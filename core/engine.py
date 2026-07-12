import pandas as pd
import numpy as np

def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    cols_lower = {str(c).lower(): c for c in df.columns}
    for alias in aliases:
        al_lower = alias.lower()
        if al_lower in cols_lower:
            return cols_lower[al_lower]
        matched = next((c for c in df.columns if al_lower in str(c).lower()), None)
        if matched:
            return matched
    return None

def _get_regional_coeff(df: pd.DataFrame, preset: dict) -> pd.Series:
    rc = preset.get("regional_coefficients", {})
    keywords = rc.get("keywords", [])
    rules = rc.get("rules", {})
    
    col_name = _find_column(df, keywords) if keywords else None
    mult = pd.Series(1.0, index=df.index)
    
    if col_name:
        addr = df[col_name].fillna("").astype(str).str.lower()
        for kw, coeff in rules.items():
            mult = mult.where(~addr.str.contains(kw, na=False), coeff)
            
    return mult

def _extract_okved_class(okved_code) -> str:
    if pd.isna(okved_code) or str(okved_code).strip() == "":
        return ""
    code = str(okved_code).strip()
    dot_pos = code.find(".")
    cls = code[:dot_pos] if dot_pos > 0 else code
    return cls.zfill(2)

def calculate_scoring(df: pd.DataFrame, preset: dict) -> pd.DataFrame:
    result = df.copy()
    region_mult = _get_regional_coeff(result, preset)
    result["_region_mult"] = region_mult
    
    all_cat_scores = []
    overall_completeness_parts = []
    
    # Store feature series for cross-referencing (like debt ratio needing revenue)
    feature_series_cache = {}
    
    for cat in preset["categories"]:
        cat_id = cat["id"]
        cat_weight = cat.get("weight", 0.0)
        
        feature_scores = []
        feature_completeness = []
        
        for feat in cat.get("features", []):
            f_id = feat["id"]
            f_weight = feat.get("weight", 0.0)
            col_name = _find_column(result, [feat.get("name", f_id)])
            
            series = result[col_name] if col_name else pd.Series(np.nan, index=result.index)
            feature_series_cache[f"{cat_id}_{f_id}"] = series
            
            method = feat.get("scoring_method", {})
            m_type = method.get("type", "")
            params = method.get("params", {})
            
            score_series = pd.Series(0.0, index=result.index)
            is_present = pd.Series(0.0, index=result.index)
            
            if m_type == "log_scale":
                threshold = params.get("threshold", 0)
                scale = params.get("scale", 20)
                apply_reg = params.get("apply_regional_coeff", False)
                
                t_series = threshold / region_mult if apply_reg else pd.Series(threshold, index=result.index)
                val = pd.to_numeric(series, errors="coerce").fillna(0)
                
                # if profit, clip to 0
                if "profit" in f_id.lower():
                    val = val.clip(lower=0)
                    
                above = val >= t_series
                ratio = np.where(above, (val - t_series) / t_series, 0)
                log_val = np.log1p(ratio) / np.log(scale)
                raw = np.where(above, np.clip(log_val, 0, 1) * 100, 0.0)
                score_series = pd.Series(np.round(raw, 1), index=result.index)
                is_present = series.notna().astype(float)
                
            elif m_type == "debt_ratio":
                threshold = params.get("threshold", 0.3)
                rev_f_id = params.get("revenue_feature", "revenue")
                rev_series = feature_series_cache.get(f"{cat_id}_{rev_f_id}", pd.Series(np.nan, index=result.index))
                
                val = pd.to_numeric(series, errors="coerce")
                rev_val = pd.to_numeric(rev_series, errors="coerce").replace(0, np.nan)
                ratio = val / rev_val
                
                score_series = pd.Series(np.where(
                    ratio.isna(),
                    0.0,
                    np.round((1 - np.clip(ratio.fillna(0).clip(lower=0) / threshold, 0, 1)) * 100, 1)
                ), index=result.index)
                is_present = series.notna().astype(float)
                
            elif m_type == "percentile_rank":
                dates = pd.to_datetime(series, errors="coerce")
                n = dates.count()
                if n <= 1:
                    score_series = pd.Series(50.0, index=result.index)
                else:
                    ranks = dates.rank(method="average")
                    score_series = np.round((n - ranks) / (n - 1) * 100, 2)
                score_series = pd.Series(np.where(dates.isna(), 0.0, score_series), index=result.index)
                is_present = dates.notna().astype(float)
                
            elif m_type == "categorical_mapping":
                mapping = params.get("mapping", {})
                def_score = params.get("default_score", 0.0)
                emp_score = params.get("empty_score", 0.0)
                
                def _map_val(v):
                    if pd.isna(v) or str(v).strip() == "":
                        return emp_score
                    return mapping.get(str(v).strip(), def_score)
                
                score_series = series.map(_map_val)
                # specific to B category RMSP: empty is fully present (100%)
                is_present = pd.Series(1.0, index=result.index) if emp_score == 100.0 else series.notna().astype(float)
                
            elif m_type == "okved_mapping":
                mapping = params.get("mapping", {})
                def_score = params.get("default_score", 0.0)
                classes = series.apply(_extract_okved_class)
                score_series = classes.map(mapping).fillna(def_score).astype(float)
                feature_series_cache[f"{cat_id}_{f_id}_class"] = classes # for stop factor
                is_present = (series.notna() & (series.astype(str).str.strip() != "")).astype(float)
                
            elif m_type == "tax_mapping":
                mapping = params.get("mapping", {})
                def_score = params.get("default_score", 0.0)
                tax_clean = series.fillna("").astype(str).str.strip().str.upper().replace({"ОСНО": "ОСН", "NAN": "", "NONE": ""})
                score_series = tax_clean.map(mapping).fillna(def_score).astype(float)
                is_present = (series.notna() & (series.astype(str).str.strip() != "")).astype(float)
                
            elif m_type == "log_score_simple":
                cap = params.get("cap", 100.0)
                sp_one = params.get("special_one", None)
                val = pd.to_numeric(series, errors="coerce")
                
                positives = val[val > 0].dropna()
                if positives.empty:
                    score_series = pd.Series(0.0, index=result.index)
                else:
                    ln_min = np.log(positives.min())
                    ln_max = np.log(positives.max())
                    if ln_max == ln_min:
                        s = np.where(val > 0, cap, 0.0)
                        if sp_one is not None:
                            s = np.where(val == 1, sp_one, s)
                        score_series = pd.Series(s, index=result.index)
                    else:
                        safe_vals = val.clip(lower=1e-10)
                        s = (np.log(safe_vals) - ln_min) / (ln_max - ln_min) * cap
                        s = np.where(val <= 0, 0.0, s)
                        s = np.clip(s, 0.0, None)
                        if sp_one is not None:
                            s = np.where(val == 1, sp_one, s)
                        score_series = pd.Series(np.round(s, 2), index=result.index)
                score_series = pd.Series(np.where(val.isna(), 0.0, score_series), index=result.index)
                is_present = val.notna().astype(float)
                
            elif m_type == "binary_presence":
                p_score = params.get("present", 100.0)
                a_score = params.get("absent", 0.0)
                is_p = series.notna() & (series.astype(str).str.strip() != "")
                score_series = pd.Series(np.where(is_p, p_score, a_score), index=result.index)
                is_present = is_p.astype(float) if p_score > a_score else pd.Series(1.0, index=result.index) # if absent is good, completeness might be 1.0 or we just use is_p?
                # Actually, D category uses count of present for completeness. 
                if a_score == 100.0: # like liquidation
                    is_present = pd.Series(1.0, index=result.index) if col_name else pd.Series(0.0, index=result.index)
                else:
                    is_present = is_p.astype(float)
                
            feature_scores.append(score_series * f_weight)
            feature_completeness.append(is_present)
            
        # Category base score
        if feature_scores:
            cat_base_score = sum(feature_scores)
        else:
            cat_base_score = pd.Series(0.0, index=result.index)
            
        # Stop factors
        stop_factor = pd.Series(1.0, index=result.index)
        for sf in cat.get("stop_factors", []):
            sf_type = sf.get("type")
            
            if sf_type == "numeric_condition":
                f_id = sf.get("feature")
                op = sf.get("operator")
                use_reg = sf.get("use_regional_coeff", False)
                
                # Need to find the threshold used for this feature
                threshold = 0
                for f in cat["features"]:
                    if f["id"] == f_id:
                        threshold = f.get("scoring_method", {}).get("params", {}).get("threshold", 0)
                        break
                        
                t_series = threshold / region_mult if use_reg else pd.Series(threshold, index=result.index)
                val = pd.to_numeric(feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(0, index=result.index)), errors="coerce").fillna(0)
                
                if op == "<":
                    stop_factor = stop_factor * np.where(val < t_series, 0, 1)
                    
            elif sf_type == "exact_value":
                f_id = sf.get("feature")
                val_check = sf.get("value")
                val = feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(np.nan, index=result.index))
                
                if isinstance(val_check, (int, float)):
                    val = pd.to_numeric(val, errors="coerce")
                    is_zero = (val == val_check)
                    stop_factor = stop_factor * np.where(is_zero, 0, 1)
                    
            elif sf_type == "missing_all":
                f_ids = sf.get("features", [])
                missing = pd.Series(True, index=result.index)
                for f_id in f_ids:
                    s = feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(np.nan, index=result.index))
                    missing = missing & (s.isna() | (s.astype(str).str.strip() == ""))
                stop_factor = stop_factor * np.where(missing, 0, 1)
                
            elif sf_type == "categorical_in":
                f_id = sf.get("feature")
                score_val = sf.get("values_with_score", 0)
                # specific to okved
                mapping = {}
                for f in cat["features"]:
                    if f["id"] == f_id:
                        mapping = f.get("scoring_method", {}).get("params", {}).get("mapping", {})
                        break
                classes_with_score = {k for k, v in mapping.items() if v == score_val}
                classes = feature_series_cache.get(f"{cat_id}_{f_id}_class", pd.Series("", index=result.index))
                stop_factor = stop_factor * np.where(classes.isin(classes_with_score), 0, 1)
                
            elif sf_type == "present":
                f_id = sf.get("feature")
                s = feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(np.nan, index=result.index))
                is_present = s.notna() & (s.astype(str).str.strip() != "")
                stop_factor = stop_factor * np.where(is_present, 0, 1)

        # Modifiers
        for mod in cat.get("category_modifiers", []):
            if mod["type"] == "zero_if_missing_all":
                f_ids = mod["features"]
                missing = pd.Series(True, index=result.index)
                for f_id in f_ids:
                    s = feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(np.nan, index=result.index))
                    missing = missing & (s.isna() | (s.astype(str).str.strip() == ""))
                cat_base_score = np.where(missing, 0.0, cat_base_score)
                
        # Diagnostic columns (do not affect scoring, for analysis only)
        for diag in cat.get("diagnostic_columns", []):
            d_type = diag.get("type")
            d_id = diag.get("id")
            if d_type == "contact_status" and len(diag.get("features", [])) >= 2:
                f1_id, f2_id = diag["features"][0], diag["features"][1]
                vals = diag.get("values", {})
                s1 = feature_series_cache.get(f"{cat_id}_{f1_id}", pd.Series(np.nan, index=result.index))
                s2 = feature_series_cache.get(f"{cat_id}_{f2_id}", pd.Series(np.nan, index=result.index))
                has_f1 = s1.notna() & (s1.astype(str).str.strip() != "")
                has_f2 = s2.notna() & (s2.astype(str).str.strip() != "")
                status = np.full(len(result), vals.get("none", "нет контактов"), dtype=object)
                status[has_f1.values & ~has_f2.values] = vals.get("phone_only", "только первый")
                status[~has_f1.values & has_f2.values] = vals.get("email_only", "только второй")
                status[has_f1.values & has_f2.values] = vals.get("both", "оба")
                result[f"{cat_id}_{d_id}"] = status
            elif d_type == "categorical_unknown":
                f_ids = diag.get("features", [])
                status_list = [[] for _ in range(len(result))]
                
                for f_id in f_ids:
                    mapping = {}
                    for f in cat.get("features", []):
                        if f["id"] == f_id:
                            mapping = f.get("scoring_method", {}).get("params", {}).get("mapping", {})
                            break
                            
                    s = feature_series_cache.get(f"{cat_id}_{f_id}", pd.Series(np.nan, index=result.index))
                    has_s = s.notna() & (s.astype(str).str.strip() != "")
                    
                    clean_s = pd.to_numeric(s, errors="coerce").astype("Int64").astype(str)
                    clean_s = np.where(clean_s == "<NA>", s.astype(str).str.strip(), clean_s)
                    
                    is_unknown = has_s & ~pd.Series(clean_s).isin(mapping.keys())
                    
                    for i, unk in enumerate(is_unknown):
                        if unk:
                            status_list[i].append(f"UNKNOWN_{f_id.upper()}")
                            
                vals = diag.get("values", {})
                none_val = vals.get("none", "OK")
                final_status = [", ".join(st) if st else none_val for st in status_list]
                result[f"{cat_id}_{d_id}"] = final_status

        # Final Category Score
        cat_final = np.round(cat_base_score, 1) * stop_factor
        result[f"{cat_id}_score"] = cat_final
        result[f"{cat_id}_stop_factor"] = stop_factor
        
        # Category completeness
        if feature_completeness:
            comp = np.round(sum(feature_completeness) / len(feature_completeness) * 100, 1)
        else:
            comp = pd.Series(0.0, index=result.index)
            
        # Legacy quirk for A completeness: if C score == 0 and revenue missing -> completeness 100%
        # This was requested to be dropped, but just to be safe I'll implement a dynamic rule if present.
        # Actually, user said: "забиваем на это. эта логика излишня". I will NOT add it.
            
        result[f"{cat_id}_completeness"] = comp
        
        all_cat_scores.append(cat_final * cat_weight)
        overall_completeness_parts.append(comp * cat_weight)

    # Total Score Calculation
    # If any category score is 0, total is 0.
    total_weighted = sum(all_cat_scores) if all_cat_scores else pd.Series(0.0, index=result.index)
    any_zero = pd.Series(False, index=result.index)
    for cat in preset["categories"]:
        cat_id = cat["id"]
        any_zero = any_zero | (result[f"{cat_id}_score"] == 0)
        
    total = np.where(any_zero, 0, np.round(total_weighted, 2))
    result["scoring_total"] = total
    
    # Enrichment priority and entropy
    enrich_w = preset.get("enrichment_weights", {"score_weight": 0.6, "entropy_weight": 0.4})
    overall_comp = sum(overall_completeness_parts) if overall_completeness_parts else pd.Series(100.0, index=result.index)
    entropy = 100.0 - overall_comp
    result["scoring_entropy"] = np.round(entropy, 1)
    
    priority = total * enrich_w["score_weight"] + entropy * enrich_w["entropy_weight"]
    result["enrichment_priority"] = np.where(any_zero, 0.0, np.round(priority, 2))
    
    # Segments
    segments = preset.get("segments", {})
    # Default to cold if not matching
    # Convert dict to sorted list of dicts by min_score desc
    seg_list = sorted([{"label": v["label"], "min_score": v["min_score"]} for k, v in segments.items()], key=lambda x: x["min_score"], reverse=True)
    
    def _assign_seg(score):
        for s in seg_list:
            if score >= s["min_score"]:
                return s["label"]
        return seg_list[-1]["label"] if seg_list else "Unknown"
        
    result["scoring_segment"] = pd.Series(total).apply(_assign_seg)
    
    return result
