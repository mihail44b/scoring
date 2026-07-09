"""
Категория A — Финансовое здоровье.

Портирование формул из листа «Категория А фин.зд» файла
ЛИК_дляСкорингаДП_v4_логарифмическая_шкала.xlsx

Метод расчёта (логарифмическая шкала):
  - Для прямых показателей (Выручка, ОС, УК):
      если значение < порог/регион_коэфф → 0
      иначе → ROUND(100 * MIN(1, LN(1+(факт-порог)/порог) / LN(scale)), 1)
  - Для прибылей (Чист. прибыль, Прибыль от продаж, Прибыль до н/о):
      если значение < порог → 0
      иначе → ROUND(100 * MIN(1, LN(1+(факт-порог)/порог) / LN(scale)), 1)
      (региональный коэффициент к прибылям НЕ применяется)
  - Для долговых коэффициентов (КЗ/Выручка, ДЗ/Выручка):
      инверсия: ROUND((1 - MIN(1, MAX(0, ratio)/порог)) * 100, 1)
  - Итоговый балл = взвешенная сумма * стоп-фактор
  - Стоп-фактор = 0 если Выручка < порог_выручки / регион_коэфф

Масштабные множители логарифма (AF114:AF119):
  Выручка, ОС, Чист.приб., Прибыль от продаж, Прибыль до н/о → scale=20
  Уставный капитал → scale=40

Региональный коэффициент (Y):
  Чувашская Республика → Y=3.0  (порог / 3 → ниже входная планка)
  Прочие регионы       → Y=1.0  (стандартный порог)
"""
import os
import json
import pandas as pd
import numpy as np

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

def _load_config():
    path = os.path.join(_CONF_DIR, "category_a_config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _load_weights():
    path = os.path.join(_CONF_DIR, "weights.json")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
        return config["categories"]["A_financial_health"]["features"]


def _detect_region_coeff(df: pd.DataFrame, regional_coeffs: dict) -> pd.Series:
    """
    Определяет региональный коэффициент Y по полю адреса.
    Соответствует формуле Y2 в Excel:
      =ЕСЛИ(X2="Чувашская Республика"; AF31; AF32)
    где X2 = ЕСЛИ(ЕЧИСЛО(ПОИСК("ЧУВАШ"; адрес)); "Чувашская Республика"; "Прочие регионы")
    """
    addr_col = next(
        (c for c in df.columns if any(
            kw in str(c).lower() for kw in ["адрес", "регион", "местонахождение"]
        )),
        None
    )

    if addr_col is None:
        return pd.Series(1.0, index=df.index)

    addr = df[addr_col].fillna("").astype(str).str.lower()
    mult = pd.Series(1.0, index=df.index)
    for keyword, coeff in regional_coeffs.items():
        mult = mult.where(~addr.str.contains(keyword, na=False), coeff)

    return mult


def _log_score(series: pd.Series, threshold: pd.Series | float, scale: int) -> pd.Series:
    """
    Логарифмическая шкала баллов:
      = ROUND(100 * MIN(1, LN(1 + (факт - порог) / порог) / LN(scale)), 1)

    Если значение < порог → 0 (стоп-фактор на уровне показателя).

    Args:
        series:    Series числовых значений
        threshold: порог (может быть скалярным или Series для региональной адаптации)
        scale:     масштабный множитель (20 или 40)
    """
    val = series.fillna(0)
    # Вычисляем логарифмический балл только когда значение >= порога
    above = val >= threshold
    ratio = np.where(above, (val - threshold) / threshold, 0)
    log_val = np.log1p(ratio) / np.log(scale)
    raw = np.where(above, np.clip(log_val, 0, 1) * 100, 0.0)
    return pd.Series(np.round(raw, 1), index=series.index)


def score_category_a(df: pd.DataFrame) -> pd.DataFrame:
    """
    Категория A — Финансовое здоровье.

    Входные данные: df со всеми исходными колонками.
    Выходные данные: df + новые колонки:
      A_score           — балл категории (0-100)
      A_completeness    — полнота данных категории (0-100%)
      A_stop_factor     — 1 если данные достаточны, 0 если стоп
      A_no_revenue_data — True если выручка отсутствует в данных (для перераспределения весов)
      A_region_coeff    — региональный коэффициент (диагностика)
    """
    result = df.copy()

    # Загрузка конфигов
    config = _load_config()
    weights = _load_weights()
    THRESHOLDS = config["thresholds"]
    LOG_SCALE = config["log_scale"]
    COLUMN_MAP = config["column_map"]
    REGIONAL_COEFFICIENTS = config["regional_coefficients"]
    WEIGHTS = weights

    # Определяем региональный коэффициент Y
    region_mult = _detect_region_coeff(result, REGIONAL_COEFFICIENTS)

    # Извлекаем сырые значения (NaN там, где данных нет)
    def get_numeric(col_prefix: str) -> pd.Series:
        matched = next(
            (c for c in result.columns if col_prefix.lower() in str(c).lower()),
            None
        )
        if not matched:
            return pd.Series(np.nan, index=result.index)
        return pd.to_numeric(result[matched], errors="coerce")

    revenue       = get_numeric(COLUMN_MAP["revenue"])
    fixed_assets  = get_numeric(COLUMN_MAP["fixed_assets"])
    charter       = get_numeric(COLUMN_MAP["charter_capital"])
    net_profit    = get_numeric(COLUMN_MAP["net_profit"])
    oper_profit   = get_numeric(COLUMN_MAP["operating_profit"])
    pretax        = get_numeric(COLUMN_MAP["pretax_profit"])
    kz            = get_numeric(COLUMN_MAP["debt_kz"])
    dz            = get_numeric(COLUMN_MAP["debt_dz"])

    # ─── Флаг: выручка отсутствует (NaN), а не равна нулю ───────────────────
    revenue_is_missing = revenue.isna()

    # ─── Скорректированные пороги для показателей с региональным влиянием ───
    # Региональный коэффициент применяется ТОЛЬКО к Выручке, ОС, УК
    thresh_rev   = THRESHOLDS["revenue"]      / region_mult   # N-формула: $AI$12/$Y2
    thresh_fa    = THRESHOLDS["fixed_assets"] / region_mult   # O-формула: $AI$13/$Y2
    thresh_uc    = THRESHOLDS["charter_capital"] / region_mult  # P-формула: $AI$14/$Y2
    thresh_np    = THRESHOLDS["net_profit"]       # Q-формула: $AI$15 (без делителя)
    thresh_op    = THRESHOLDS["operating_profit"] # R-формула: $AI$16
    thresh_pt    = THRESHOLDS["pretax_profit"]    # S-формула: $AI$17

    # ─── Логарифмические баллы (прямые показатели) ───────────────────────────
    # Формула N2: =ЕСЛИ(D2<$AI$12/$Y2; 0; ОКРУГЛ(100*МИН(1;LN(1+(D2-$AI$12/$Y2)/($AI$12/$Y2))/LN($AF$114)); 1))
    score_revenue = _log_score(revenue, thresh_rev, LOG_SCALE["revenue"])
    score_fixed   = _log_score(fixed_assets, thresh_fa, LOG_SCALE["fixed_assets"])
    score_charter = _log_score(charter, thresh_uc, LOG_SCALE["charter_capital"])

    # Для прибылей: убыток (< 0) также даёт 0 (меньше порога)
    score_net_profit  = _log_score(net_profit.clip(lower=0),  thresh_np, LOG_SCALE["net_profit"])
    score_oper_profit = _log_score(oper_profit.clip(lower=0), thresh_op, LOG_SCALE["operating_profit"])
    score_pretax      = _log_score(pretax.clip(lower=0),      thresh_pt, LOG_SCALE["pretax_profit"])

    # ─── Баллы по долговым коэффициентам (инверсия, без лог-шкалы) ──────────
    # Формула T2: =ЕСЛИ(L2=""; 0; ОКРУГЛ((1-МИН(1;МАКС(0;L2)/$AI$18))*100; 1))
    ratio_kz = kz  / revenue.replace(0, np.nan)
    ratio_dz = dz  / revenue.replace(0, np.nan)

    score_kz = pd.Series(np.where(
        ratio_kz.isna(),
        0.0,
        np.round((1 - np.clip(ratio_kz.fillna(0).clip(lower=0) / THRESHOLDS["debt_kz_ratio"], 0, 1)) * 100, 1)
    ), index=result.index)

    score_dz = pd.Series(np.where(
        ratio_dz.isna(),
        0.0,
        np.round((1 - np.clip(ratio_dz.fillna(0).clip(lower=0) / THRESHOLDS["debt_dz_ratio"], 0, 1)) * 100, 1)
    ), index=result.index)

    # ─── Итоговый балл (взвешенная сумма) ────────────────────────────────────
    # Формула V2: =ОКРУГЛ(N2*AH12 + O2*AH13 + ... + U2*AH19; 1) * W2
    total = np.round(
        score_revenue     * WEIGHTS["revenue"]
        + score_fixed     * WEIGHTS["fixed_assets"]
        + score_charter   * WEIGHTS["charter_capital"]
        + score_net_profit  * WEIGHTS["net_profit"]
        + score_oper_profit * WEIGHTS["operating_profit"]
        + score_pretax    * WEIGHTS["pretax_profit"]
        + score_kz        * WEIGHTS["debt_kz"]
        + score_dz        * WEIGHTS["debt_dz"],
        1
    )

    # ─── Стоп-фактор W2 ─────────────────────────────────────────────────────
    # Формула: =ЕСЛИ(D2 < $AI$12/$Y2; 0; 1)
    stop_factor = pd.Series(np.where(
        revenue.fillna(0) < thresh_rev, 0, 1
    ), index=result.index)

    # ─── Полнота данных ──────────────────────────────────────────────────────
    fields = [revenue, fixed_assets, charter, net_profit, oper_profit, pretax, kz, dz]
    available = sum(~f.isna() for f in fields)
    completeness = np.round(available / len(fields) * 100, 1)

    # Если выручка отсутствует И в категории C стоит 0 (нецелевая отрасль) —
    # полнота считается 100%, так как обогащение данных для таких компаний не нужно
    c_score = result.get("C_score", pd.Series(np.nan, index=result.index))
    completeness = np.where(
        revenue_is_missing & (c_score == 0),
        100.0,
        completeness
    )

    # ─── Запись результатов ──────────────────────────────────────────────────
    result["A_score"]           = np.round(total * stop_factor, 1)
    result["A_completeness"]    = completeness
    result["A_stop_factor"]     = stop_factor
    result["A_no_revenue_data"] = revenue_is_missing
    result["A_region_coeff"]    = region_mult

    return result
