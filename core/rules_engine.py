"""
Rules Engine — применение весов категорий, стоп-факторов и сегментации.

Веса из config/weights.json, стоп-факторы из категорийных модулей.

"""
import os
import pandas as pd
import numpy as np
import json


def _load_weights() -> dict:
    """Загружает веса из JSON-конфига."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "weights.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    cats = config["categories"]
    return {
        "A": cats["A_financial_health"]["weight"],
        "B": cats["B_scale_maturity"]["weight"],
        "C": cats["C_industry_relevance"]["weight"],
        "D": cats["D_contact_availability"]["weight"],
        "E": cats["E_legal_status"]["weight"],
    }


def _load_segments() -> list[dict]:
    """Загружает пороги сегментов из JSON."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "weights.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    segs = config["segments"]
    return [
        {"min": segs["hot"]["min_score"], "label": segs["hot"]["label"]},
        {"min": segs["warm"]["min_score"], "label": segs["warm"]["label"]},
        {"min": segs["cold"]["min_score"], "label": segs["cold"]["label"]},
    ]


def _load_enrichment_weights() -> dict:
    """Загружает веса для приоритета обогащения."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "enrichment_weights.json"
    )
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"score_weight": 0.6, "entropy_weight": 0.4}


def apply_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Рассчитывает итоговый скоринг и сегмент.

    Логика:
      1. Стандартный расчёт: A*wA + B*wB + C*wC + D*wD + E*wE
      2. Если хотя бы одна категория == 0 → итог = 0

    Args:
        df: DataFrame с колонками A_score..E_score

    Returns:
        df с колонками: scoring_total, scoring_segment, scoring_entropy, enrichment_priority
    """
    result = df.copy()
    weights = _load_weights()
    segments = _load_segments()

    a = result.get("A_score", pd.Series(0, index=result.index)).fillna(0)
    b = result.get("B_score", pd.Series(0, index=result.index)).fillna(0)
    c = result.get("C_score", pd.Series(0, index=result.index)).fillna(0)
    d = result.get("D_score", pd.Series(0, index=result.index)).fillna(0)
    e = result.get("E_score", pd.Series(0, index=result.index)).fillna(0)

    # Если хотя бы одна категория = 0, итоговый скор = 0
    any_zero = (a == 0) | (b == 0) | (c == 0) | (d == 0) | (e == 0)

    weighted = (
        a * weights["A"]
        + b * weights["B"]
        + c * weights["C"]
        + d * weights["D"]
        + e * weights["E"]
    )

    total = np.where(any_zero, 0, np.round(weighted, 2))
    result["scoring_total"] = total

    # ─── Расчет энтропии и приоритета обогащения ─────────────────────
    enrich_weights = _load_enrichment_weights()
    a_comp = result.get("A_completeness", pd.Series(0, index=result.index)).fillna(0)
    b_comp = result.get("B_completeness", pd.Series(0, index=result.index)).fillna(0)
    c_comp = result.get("C_completeness", pd.Series(0, index=result.index)).fillna(0)
    d_comp = result.get("D_completeness", pd.Series(0, index=result.index)).fillna(0)
    e_comp = result.get("E_completeness", pd.Series(0, index=result.index)).fillna(0)

    overall_completeness = (
        a_comp * weights["A"]
        + b_comp * weights["B"]
        + c_comp * weights["C"]
        + d_comp * weights["D"]
        + e_comp * weights["E"]
    )
    
    entropy = 100.0 - overall_completeness
    result["scoring_entropy"] = np.round(entropy, 1)

    priority = total * enrich_weights["score_weight"] + entropy * enrich_weights["entropy_weight"]
    result["enrichment_priority"] = np.where(any_zero, 0.0, np.round(priority, 2))

    # ─── Сегментация ─────────────────────────────────────────────────
    def assign_segment(score):
        for seg in segments:
            if score >= seg["min"]:
                return seg["label"]
        return segments[-1]["label"]

    result["scoring_segment"] = pd.Series(total).apply(assign_segment)

    return result
