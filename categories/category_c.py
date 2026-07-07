"""
Категория C — Отраслевая релевантность (участник 3).

Признаки и веса: ОКВЭД (0.80), Налоговый режим (0.20).
Стоп-фактор: класс ОКВЭД в Тир 4 (бюджет/НКО).
"""
import os
import pandas as pd
import numpy as np
import json

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
WEIGHT_OKVED = 0.80
WEIGHT_TAX = 0.20
DEFAULT_SCORE = 50


def _load_okved_tiers() -> dict:
    path = os.path.join(_CONF_DIR, "okved_tiers.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def _load_tax_regimes() -> dict:
    path = os.path.join(_CONF_DIR, "tax_regimes.json")
    if not os.path.exists(path):
        return {"ОСН": 100, "УСН": 50, "ЕСХН": 40}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_class(okved_code) -> str:
    if pd.isna(okved_code) or str(okved_code).strip() == "":
        return ""
    code = str(okved_code).strip()
    dot_pos = code.find(".")
    return code[:dot_pos] if dot_pos > 0 else code


def score_category_c(df: pd.DataFrame) -> pd.DataFrame:
    """
    Вход: df со всеми колонками. Выход: df + C_score, C_completeness, C_stop_factor.
    """
    result = df.copy()
    okved_tiers = _load_okved_tiers()
    tax_regimes = _load_tax_regimes()

    def get_series(col_prefix):
        matched_col = next((c for c in result.columns if col_prefix.lower() in str(c).lower()), None)
        return result[matched_col] if matched_col else None

    okved_col = get_series("ОКВЭД")
    classes = okved_col.apply(_extract_class) if okved_col is not None else pd.Series("", index=result.index)
    score_okved = classes.map(okved_tiers).fillna(DEFAULT_SCORE).astype(float)

    tax_col = get_series("Налоговый режим")
    if tax_col is not None:
        score_tax = tax_col.astype(str).str.strip().map(tax_regimes).fillna(DEFAULT_SCORE).astype(float)
    else:
        score_tax = pd.Series(DEFAULT_SCORE, index=result.index, dtype=float)

    tier4_classes = {code for code, score in okved_tiers.items() if score == 0}
    stop_factor = np.where(classes.isin(tier4_classes), 0, 1)

    total = (WEIGHT_OKVED * score_okved + WEIGHT_TAX * score_tax) * stop_factor

    has_okved = (okved_col.notna() & (okved_col.astype(str).str.strip() != "")).astype(int) if okved_col is not None else 0
    has_tax = (tax_col.notna() & (tax_col.astype(str).str.strip() != "")).astype(int) if tax_col is not None else 0
    completeness = np.round((has_okved + has_tax) / 2 * 100, 1)

    result["C_score"] = np.round(total, 1)
    result["C_completeness"] = completeness
    result["C_stop_factor"] = stop_factor
    return result
