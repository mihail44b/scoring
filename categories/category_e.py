"""
Категория E — Юридический статус и риски (участник 4).
"""
import os
import pandas as pd
import numpy as np
import json

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

E_WEIGHTS = {
    "liquidation": 0.4,
    "okfs":        0.3,
    "okopf":       0.2,
    "inn_manager": 0.1,
}

DEFAULT_OKFS_SCORE = 50
DEFAULT_OKOPF_SCORE = 50

def _load_okfs() -> dict:
    path = os.path.join(_CONF_DIR, "okfs.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f).items()}

def _load_okopf() -> dict:
    path = os.path.join(_CONF_DIR, "okopf.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f).items()}

def _get_series(df, col_prefix):
    matched_col = next((c for c in df.columns if col_prefix.lower() in str(c).lower()), None)
    return df[matched_col] if matched_col else None

def score_category_e(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    okfs_map = _load_okfs()
    okopf_map = _load_okopf()

    liq_col = _get_series(result, "Ликвидация")
    if liq_col is not None:
        s_liq = np.where(
            liq_col.isna() | (liq_col.astype(str).str.strip() == ""),
            100, 0
        ).astype(float)
    else:
        s_liq = np.full(len(result), 100.0)

    okfs_col = _get_series(result, "ОКФС")
    if okfs_col is not None:
        okfs_int = pd.to_numeric(okfs_col, errors="coerce")
        s_okfs = okfs_int.map(okfs_map).fillna(DEFAULT_OKFS_SCORE).astype(float)
    else:
        s_okfs = pd.Series(DEFAULT_OKFS_SCORE, index=result.index, dtype=float)

    okopf_col = _get_series(result, "ОКОПФ")
    if okopf_col is not None:
        okopf_int = pd.to_numeric(okopf_col, errors="coerce")
        s_okopf = okopf_int.map(okopf_map).fillna(DEFAULT_OKOPF_SCORE).astype(float)
    else:
        s_okopf = pd.Series(DEFAULT_OKOPF_SCORE, index=result.index, dtype=float)

    inn_col = _get_series(result, "ИНН руководителя")
    if inn_col is not None:
        s_inn = np.where(
            inn_col.isna() | (inn_col.astype(str).str.strip() == ""),
            50, 100
        ).astype(float)
    else:
        s_inn = np.full(len(result), 50.0)

    stop = np.where(s_liq == 100, 1, 0)
    total = np.where(
        s_liq == 0, 0,
        s_liq * E_WEIGHTS["liquidation"]
        + s_okfs * E_WEIGHTS["okfs"]
        + s_okopf * E_WEIGHTS["okopf"]
        + s_inn * E_WEIGHTS["inn_manager"]
    ) * stop

    fields = [liq_col, okfs_col, okopf_col, inn_col]
    n = len([f for f in fields if f is not None])
    count_present = sum(
        (f.notna() & (f.astype(str).str.strip() != "")).astype(int)
        for f in fields if f is not None
    )
    completeness = np.round(count_present / max(n, 1) * 100, 1) if n > 0 else 0

    result["E_score"] = np.round(total, 1)
    result["E_completeness"] = completeness
    result["E_stop_factor"] = stop
    return result
