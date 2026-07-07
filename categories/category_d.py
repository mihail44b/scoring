"""
Категория D — Доступность контакта (участник 4).
"""
import pandas as pd
import numpy as np

# ─── Веса категории D (из формулы P2 в Excel) ───────────────────────────
D_WEIGHTS = {
    "phone":    0.25,
    "email":    0.25,
    "website":  0.20,
    "address":  0.15,
    "manager":  0.10,
    "position": 0.05,
}

def _get_series(df, col_prefix):
    matched_col = next((c for c in df.columns if col_prefix.lower() in str(c).lower()), None)
    return df[matched_col] if matched_col else None

def _is_present(series) -> np.ndarray:
    if series is None:
        return np.zeros(0)
    return np.where(
        series.notna() & (series.astype(str).str.strip() != ""),
        100, 0
    ).astype(float)

def score_category_d(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    s_phone = _is_present(_get_series(result, "Телефоны"))
    s_web = _is_present(_get_series(result, "Web-сайты"))
    s_email = _is_present(_get_series(result, "Email"))
    s_addr = _is_present(_get_series(result, "Адрес"))
    s_mgr = _is_present(_get_series(result, "Руководитель"))
    s_pos = _is_present(_get_series(result, "Должность"))

    stop = np.where((s_phone == 0) & (s_email == 0), 0, 1)

    weighted = (
        s_phone * D_WEIGHTS["phone"]
        + s_email * D_WEIGHTS["email"]
        + s_web * D_WEIGHTS["website"]
        + s_addr * D_WEIGHTS["address"]
        + s_mgr * D_WEIGHTS["manager"]
        + s_pos * D_WEIGHTS["position"]
    )
    total = np.where(
        (s_phone == 0) & (s_web == 0) & (s_addr == 0) & (s_email == 0),
        0, weighted
    ) * stop

    n_fields = 6
    count_present = (
        (s_phone > 0).astype(int) + (s_web > 0).astype(int) +
        (s_email > 0).astype(int) + (s_addr > 0).astype(int) +
        (s_mgr > 0).astype(int) + (s_pos > 0).astype(int)
    )
    completeness = np.round(count_present / n_fields * 100, 1)

    result["D_score"] = np.round(total, 1)
    result["D_completeness"] = completeness
    result["D_stop_factor"] = stop
    return result
