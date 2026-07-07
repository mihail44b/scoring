"""
Категория B — Масштаб и зрелость (участник 2).

Портирование формул из листа «Категория В масштаб и зрелость» рабочей Excel-модели.

Признаки:
  - Регистрация: процентный ранг (чем старше, тем выше балл)
  - РМСП: бинарный (есть/нет в реестре МСП)
  - Кол-во сотрудников: логарифмический балл
  - Запасы (2025): процентный ранг

Веса из Excel:
  Регистрация = 0.40, РМСП = 0.25, Сотрудники = 0.20, Запасы = 0.15
"""
import pandas as pd
import numpy as np
from datetime import datetime


# ─── Веса признаков ─────────────────────────────────────────────────────
WEIGHTS = {
    "registration": 0.40,
    "rmsp":         0.25,
    "employees":    0.20,
    "reserves":     0.15,
}

# ─── Маппинг колонок ─────────────────────────────────────────────────────
COLUMN_MAP = {
    "registration": "Регистрация",
    "rmsp":         "РМСП",
    "employees":    "кол-во сотрудников",
    "reserves":     "Запасы",
}


def _percentile_rank(series: pd.Series) -> pd.Series:
    """
    Аналог Excel ПРОЦЕНТРАНГ.ВКЛ → rank(pct=True) * 100.
    Пропуски заменяются средним значением (паттерн из Excel).
    """
    filled = series.copy()
    mean_val = filled.mean()
    filled = filled.fillna(mean_val)
    n = filled.count()
    if n <= 1:
        return pd.Series(50.0, index=series.index)
    ranks = filled.rank(method="average")
    return np.round((n - ranks) / (n - 1) * 100, 2)


def _log_score(series: pd.Series) -> pd.Series:
    """
    Логарифмический балл для количества сотрудников.
    Формула из Excel:
      IF(val <= 0, 0, (LN(val) - LN(MIN)) / (LN(MAX) - LN(MIN)) * 100)
    Пропуски заменяются средним.
    """
    filled = series.copy()
    mean_val = filled.mean()
    filled = filled.fillna(mean_val)
    filled = filled.clip(lower=1)  # Защита от log(0)

    ln_vals = np.log(filled)
    ln_min = ln_vals.min()
    ln_max = ln_vals.max()

    if ln_max == ln_min:
        return pd.Series(50.0, index=series.index)

    return np.round((ln_vals - ln_min) / (ln_max - ln_min) * 100, 2)


def score_category_b(df: pd.DataFrame) -> pd.DataFrame:
    """
    Категория B — Масштаб и зрелость.

    Вход: df со всеми исходными колонками (полный датасет).
    Выход: тот же df + новые колонки:
      B_score          — балл категории (0-100)
      B_completeness   — полнота данных категории (0-100%)
      B_stop_factor    — 1 если данные достаточны, 0 если стоп
    """
    result = df.copy()

    def get_series(col_prefix):
        matched_col = next((c for c in result.columns if col_prefix.lower() in str(c).lower()), None)
        return result[matched_col] if matched_col else None

    # ─── Регистрация: percentile rank ────────────────────────────────────
    reg_col = get_series(COLUMN_MAP["registration"])
    if reg_col is not None:
        reg_dates = pd.to_datetime(reg_col, errors="coerce")
        score_reg = _percentile_rank(reg_dates)
    else:
        score_reg = pd.Series(0.0, index=result.index)
        reg_dates = pd.Series(pd.NaT, index=result.index)

    # ─── РМСП: бинарный (есть запись → 100, нет → 0) ────────────────────
    rmsp_col = get_series(COLUMN_MAP["rmsp"])
    if rmsp_col is not None:
        score_rmsp = np.where(
            rmsp_col.notna() & (rmsp_col.astype(str).str.strip() != ""),
            100, 0
        ).astype(float)
    else:
        score_rmsp = np.zeros(len(result))

    # ─── Сотрудники: логарифмический балл ────────────────────────────────
    emp_col = get_series(COLUMN_MAP["employees"])
    if emp_col is not None:
        employees = pd.to_numeric(emp_col, errors="coerce")
        score_emp = _log_score(employees)
    else:
        score_emp = pd.Series(0.0, index=result.index)
        employees = pd.Series(np.nan, index=result.index)

    # ─── Запасы: percentile rank ─────────────────────────────────────────
    res_col = get_series(COLUMN_MAP["reserves"])
    if res_col is not None:
        reserves = pd.to_numeric(res_col, errors="coerce")
        score_res = _percentile_rank(reserves)
    else:
        score_res = pd.Series(0.0, index=result.index)
        reserves = pd.Series(np.nan, index=result.index)

    # ─── Стоп-фактор ────────────────────────────────────────────────────
    # Формула: IF(OR(H=0, I=0, J=0, K=0), 0, 1)
    stop_factor = np.where(
        (score_reg == 0) | (score_rmsp == 0) | (score_emp == 0) | (score_res == 0),
        0, 1
    )

    # ─── Итоговый балл ──────────────────────────────────────────────────
    # Формула: ROUND(IF(OR(M=0), 0, H*0.4 + I*0.25 + J*0.2 + K*0.15), 2)
    total = np.round(
        score_reg * WEIGHTS["registration"]
        + score_rmsp * WEIGHTS["rmsp"]
        + score_emp * WEIGHTS["employees"]
        + score_res * WEIGHTS["reserves"],
        2
    )
    total = total * stop_factor

    # ─── Полнота ─────────────────────────────────────────────────────────
    fields_available = (
        reg_dates.notna().astype(int)
        + (rmsp_col.notna() & (rmsp_col.astype(str).str.strip() != "")).astype(int) if rmsp_col is not None else 0
        + employees.notna().astype(int) if isinstance(employees, pd.Series) else 0
        + reserves.notna().astype(int) if isinstance(reserves, pd.Series) else 0
    )
    completeness = np.round(fields_available / 4 * 100, 1)

    # ─── Запись результатов ──────────────────────────────────────────────
    result["B_score"] = np.round(total, 2)
    result["B_completeness"] = completeness
    result["B_stop_factor"] = stop_factor

    return result
