"""
Категория B — Масштаб и зрелость

Портирование формул из листа «Категория В масштаб и зрелость» рабочей Excel-модели.

Признаки:
  - Регистрация: процентный ранг (чем старше, тем выше балл)
  - РМСП: градация (пусто→100, Микро→25, Малое→50, Среднее→75)
  - Кол-во сотрудников: логарифмический балл
  - Запасы (2025): логарифмический балл

Стоп-фактор: если "Кол-во сотрудников" или "Запасы" = 0 (заполнено нулём,
не пусто) → B_score = 0. Пустая ячейка НЕ является стоп-фактором — она
просто даёт 0 баллов по своему признаку.

Веса из Excel:
  Регистрация = 0.30, РМСП = 0.30, Сотрудники = 0.25, Запасы = 0.15
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

def _load_config():
    path = os.path.join(_CONF_DIR, "category_b_config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _load_weights():
    path = os.path.join(_CONF_DIR, "weights.json")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
        return config["categories"]["B_scale_maturity"]["features"]

# Аналог Excel ПРОЦЕНТРАНГ.ВКЛ → rank(pct=True) * 100.
def _percentile_rank(series: pd.Series) -> pd.Series:

    n = series.count()
    if n <= 1:
        return pd.Series(50.0, index=series.index)
    ranks = series.rank(method="average")
    return np.round((n - ranks) / (n - 1) * 100, 2)


def _log_score(series: pd.Series, cap: float = 100.0, special_one: float | None = None) -> pd.Series:
    """
    Логарифмический балл.
    Args:
        series:      числовой ряд (сотрудники или запасы)
        cap:         верхняя граница шкалы
        special_one: фиксированный балл при val=1
    """
    # Min и Max из положительных значений исходного ряда
    positives = series[series > 0].dropna()
    if positives.empty:
        return pd.Series(0.0, index=series.index)

    ln_min = np.log(positives.min())
    ln_max = np.log(positives.max())

    if ln_max == ln_min:
        scores = np.where(series > 0, cap, 0.0)
        if special_one is not None:
            scores = np.where(series == 1, special_one, scores)
        return pd.Series(scores, index=series.index)

    # Вычисление
    safe_vals = series.clip(lower=1e-10)  # защита от log(≤0)
    scores = (np.log(safe_vals) - ln_min) / (ln_max - ln_min) * cap

    # val ≤ 0 тогда 0
    scores = np.where(series <= 0, 0.0, scores)

    # Защита от отрицательных баллов
    scores = np.clip(scores, 0.0, None)

    # Спец. условие: val = 1 тогда фиксированный балл
    if special_one is not None:
        scores = np.where(series == 1, special_one, scores)

    return pd.Series(np.round(scores, 2), index=series.index)

def _rmsp_score(series: pd.Series, mapping: dict) -> pd.Series:

    def _score_one(val):
        if pd.isna(val) or str(val).strip() == "":
            return 100.0
        return mapping.get(str(val).strip(), 100.0)

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

    # Загрузка конфигов
    config = _load_config()
    weights = _load_weights()
    COLUMN_MAP = config["column_map"]
    MAPPING = config["rmsp_mapping"]
    WEIGHTS = weights

    def get_series(col_prefix):
        
        # Сначала точное совпадение имени колонки (без учёта регистра), затем — по вхождению подстроки.

        cols_lower = {str(c).lower(): c for c in result.columns}

        if col_prefix.lower() in cols_lower:
            return result[cols_lower[col_prefix.lower()]]
        matched_col = next((c for c in result.columns if col_prefix.lower() in str(c).lower()), None)
        return result[matched_col] if matched_col else None

    # Регистрация:
    reg_col = get_series(COLUMN_MAP["registration"])
    if reg_col is not None:
        reg_dates = pd.to_datetime(reg_col, errors="coerce")
        score_reg = _percentile_rank(reg_dates)
        score_reg = pd.Series(np.where(reg_dates.isna(), 0.0, score_reg), index=result.index)
    else:
        score_reg = pd.Series(0.0, index=result.index)
        reg_dates = pd.Series(pd.NaT, index=result.index)

    # РМСП:
    rmsp_col = get_series(COLUMN_MAP["rmsp"])
    if rmsp_col is not None:
        score_rmsp = _rmsp_score(rmsp_col, MAPPING)
    else:
        score_rmsp = pd.Series(100.0, index=result.index)  # нет колонки → считаем крупной

    # Сотрудники:
    emp_col = get_series(COLUMN_MAP["employees"])
    if emp_col is not None:
        employees = pd.to_numeric(emp_col, errors="coerce")
        score_emp = _log_score(employees, cap=100.0, special_one=1.0)
        score_emp = pd.Series(np.where(employees.isna(), 0.0, score_emp), index=result.index)
    else:
        score_emp = pd.Series(0.0, index=result.index)
        employees = pd.Series(np.nan, index=result.index)

    # Запасы:
    res_col = get_series(COLUMN_MAP["reserves"])
    if res_col is not None:
        reserves = pd.to_numeric(res_col, errors="coerce")
        score_res = _log_score(reserves, cap=100.0)
        score_res = pd.Series(np.where(reserves.isna(), 0.0, score_res), index=result.index)
    else:
        score_res = pd.Series(0.0, index=result.index)
        reserves = pd.Series(np.nan, index=result.index)

    # Стоп-фактор
    # Срабатывает, только если ячейка ЗАПОЛНЕНА и содержит именно 0.
    # Пустая ячейка (NaN) стоп-фактор не вызывает — она просто даёт 0 баллов
    is_zero_emp = (employees == 0)
    is_zero_res = (reserves == 0)

    stop_factor = np.where(
        is_zero_emp | is_zero_res,
        0, 1
    )

    # Итоговый балл
    total = np.round(
        score_reg * WEIGHTS["registration"]
        + score_rmsp * WEIGHTS["rmsp"]
        + score_emp * WEIGHTS["employees"]
        + score_res * WEIGHTS["reserves"],
        2
    )
    total = total * stop_factor

    # Полнота 
    reg_ok = reg_dates.notna().astype(int)
    rmsp_ok = pd.Series(1, index=result.index)  # РМСП: пусто = валидное состояние → всегда 1
    emp_ok = employees.notna().astype(int) if isinstance(employees, pd.Series) else 0
    res_ok = reserves.notna().astype(int) if isinstance(reserves, pd.Series) else 0
    fields_available = reg_ok + rmsp_ok + emp_ok + res_ok
    completeness = np.round(fields_available / 4 * 100, 1)

    # Запись результатов
    result["B_score"] = np.round(total, 2)
    result["B_completeness"] = completeness
    result["B_stop_factor"] = stop_factor

    return result