"""
Категория B — Масштаб и зрелость (участник 2).

Портирование формул из листа «Категория В масштаб и зрелость» рабочей Excel-модели.

Признаки:
  - Регистрация: процентный ранг (чем старше, тем выше балл)
  - РМСП: градация (пусто→100, Микро→25, Малое→50, Среднее→75)
  - Кол-во сотрудников: логарифмический балл (cap=60, val=1→1)
  - Запасы (2025): логарифмический балл (cap=100)

Стоп-фактор: если любой из 4 баллов = 0 → B_score = 0.

Веса из Excel:
  Регистрация = 0.40, РМСП = 0.25, Сотрудники = 0.20, Запасы = 0.15
"""
import pandas as pd
import numpy as np
from datetime import datetime


# ─── Веса признаков ─────────────────────────────────────────────────────
WEIGHTS = {
    "registration": 0.30,
    "rmsp":         0.30,
    "employees":    0.25,
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


def _log_score(series: pd.Series, cap: float = 100.0, special_one: float | None = None) -> pd.Series:
    """
    Логарифмический балл.
    Формула из Excel:
      IF(val=1 и special_one задан, special_one,
         IF(val <= 0, 0,
            (LN(val) - LN(MIN_POSITIVE)) / (LN(MAX) - LN(MIN_POSITIVE)) * cap))
    Пропуски заменяются средним.

    Args:
        series:      числовой ряд (сотрудники или запасы)
        cap:         верхняя граница шкалы (60 для сотрудников, 100 для запасов)
        special_one: фиксированный балл при val=1 (1.0 для сотрудников, None для запасов)
    """
    filled = series.copy()
    mean_val = filled.mean()
    filled = filled.fillna(mean_val)

    # Min и Max из положительных значений исходного ряда (MINIFS(>0), МАКС)
    positives = series[series > 0].dropna()
    if positives.empty:
        return pd.Series(0.0, index=series.index)

    ln_min = np.log(positives.min())
    ln_max = np.log(positives.max())

    if ln_max == ln_min:
        return pd.Series(
            np.where(filled > 0, cap, 0.0), index=series.index
        )

    # Вычисление: (LN(val) - LN(min_pos)) / (LN(max) - LN(min_pos)) * cap
    safe_vals = filled.clip(lower=1e-10)  # защита от log(≤0)
    scores = (np.log(safe_vals) - ln_min) / (ln_max - ln_min) * cap

    # val ≤ 0 → 0
    scores = np.where(filled <= 0, 0.0, scores)
    # Защита от отрицательных баллов (edge case: mean < min_positive)
    scores = np.clip(scores, 0.0, None)

    # Спец. условие: val = 1 → фиксированный балл
    if special_one is not None:
        scores = np.where(filled == 1, special_one, scores)

    return pd.Series(np.round(scores, 2), index=series.index)


def _rmsp_score(series: pd.Series) -> pd.Series:
    """
    Балл РМСП (реестр МСП).
    Формула из Excel:
      IFS(ЕПУСТО → 100, Микро → 25, Малое → 50, Среднее → 75)
    Пустое значение = компания не в реестре МСП = крупная → 100.
    Неизвестное значение = вероятно переросла порог среднего → 100.
    """
    MAPPING = {
        "Микропредприятие": 25.0,
        "Малое предприятие": 50.0,
        "Среднее предприятие": 75.0,
    }

    def _score_one(val):
        if pd.isna(val) or str(val).strip() == "":
            return 100.0
        return MAPPING.get(str(val).strip(), 100.0)

    return series.map(_score_one)


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
        score_reg = pd.Series(np.where(reg_dates.isna(), 0.0, score_reg), index=result.index)
    else:
        score_reg = pd.Series(0.0, index=result.index)
        reg_dates = pd.Series(pd.NaT, index=result.index)

    # ─── РМСП: градация (пусто→100, Микро→25, Малое→50, Среднее→75) ────
    rmsp_col = get_series(COLUMN_MAP["rmsp"])
    if rmsp_col is not None:
        score_rmsp = _rmsp_score(rmsp_col)
    else:
        score_rmsp = pd.Series(100.0, index=result.index)  # нет колонки → считаем крупной

    # ─── Сотрудники: логарифмический балл (cap=60, val=1→1) ──────────────
    emp_col = get_series(COLUMN_MAP["employees"])
    if emp_col is not None:
        employees = pd.to_numeric(emp_col, errors="coerce")
        score_emp = _log_score(employees, cap=60.0, special_one=1.0)
        score_emp = pd.Series(np.where(employees.isna(), 0.0, score_emp), index=result.index)
    else:
        score_emp = pd.Series(0.0, index=result.index)
        employees = pd.Series(np.nan, index=result.index)

    # ─── Запасы: логарифмический балл (cap=100) ────────────────────────────
    res_col = get_series(COLUMN_MAP["reserves"])
    if res_col is not None:
        reserves = pd.to_numeric(res_col, errors="coerce")
        score_res = _log_score(reserves, cap=100.0)
        score_res = pd.Series(np.where(reserves.isna(), 0.0, score_res), index=result.index)
    else:
        score_res = pd.Series(0.0, index=result.index)
        reserves = pd.Series(np.nan, index=result.index)

    # ─── Стоп-фактор ────────────────────────────────────────────────────
    # Стоп-фактор срабатывает только если балл равен 0 и ячейка была заполненной (не пустой)
    is_zero_reg = (score_reg == 0) & reg_dates.notna()
    is_zero_rmsp = (score_rmsp == 0) & (rmsp_col.notna() if rmsp_col is not None else False)
    is_zero_emp = (score_emp == 0) & employees.notna()
    is_zero_res = (score_res == 0) & reserves.notna()

    stop_factor = np.where(
        is_zero_reg | is_zero_rmsp | is_zero_emp | is_zero_res,
        0, 1
    )

    # ─── Итоговый балл ──────────────────────────────────────────────────
    # Формула: ROUND(IF(OR(M=0), 0, H*w_reg + I*w_rmsp + J*w_emp + K*w_res), 2)
    total = np.round(
        score_reg * WEIGHTS["registration"]
        + score_rmsp * WEIGHTS["rmsp"]
        + score_emp * WEIGHTS["employees"]
        + score_res * WEIGHTS["reserves"],
        2
    )
    total = total * stop_factor

    # ─── Полнота ─────────────────────────────────────────────────────────
    reg_ok = reg_dates.notna().astype(int)
    rmsp_ok = pd.Series(1, index=result.index)  # РМСП: пусто = валидное состояние → всегда 1
    emp_ok = employees.notna().astype(int) if isinstance(employees, pd.Series) else 0
    res_ok = reserves.notna().astype(int) if isinstance(reserves, pd.Series) else 0
    fields_available = reg_ok + rmsp_ok + emp_ok + res_ok
    completeness = np.round(fields_available / 4 * 100, 1)

    # ─── Запись результатов ──────────────────────────────────────────────
    result["B_score"] = np.round(total, 2)
    result["B_completeness"] = completeness
    result["B_stop_factor"] = stop_factor

    return result
