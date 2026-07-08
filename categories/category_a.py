"""
Категория A — Финансовое здоровье (участник 1).

Портирование формул из листа «Категория А фин.зд» рабочей Excel-модели.

Метод расчёта:
  - Для каждого финансового показателя: x_norm = min(1, факт / порог) * 100
  - Для долговых коэффициентов (КЗ/Выручка, ДЗ/Выручка): инверсия (1 - ratio/порог)
  - Итоговый балл = взвешенная сумма по 8 признакам * стоп-фактор
  - Стоп-фактор = 0 если Выручка < порога Выручки (360 млн)
  - Региональный коэффициент: для компаний Чувашской Республики
    порог выручки снижается пропорционально (Москва: 30 млн → Чувашия: 10 млн),
    что даёт повышающий коэффициент ~60% к финансовому скорингу

Пороги и веса из таблицы «ВЕСА И ПОРОГИ» (строки 1009-1019 листа Excel).
"""
import pandas as pd
import numpy as np


# ─── Пороги (target) и веса из Excel ───────────────────────────────────────
# Источник: строки D1011:E1018 листа «Категория А фин.зд»
THRESHOLDS = {
    "revenue":            360_000_000,   # Выручка — порог 360 млн ₽/год
    "fixed_assets":        50_000_000,   # Осн. средства — 50 млн ₽
    "charter_capital":     10_000_000,   # Уст. капитал — 10 млн ₽
    "net_profit":          30_000_000,   # Чистая прибыль — 30 млн ₽
    "operating_profit":    35_000_000,   # Прибыль от продаж — 35 млн ₽
    "pretax_profit":       30_000_000,   # Прибыль до н/о — 30 млн ₽
    "debt_kz_ratio":       0.3,          # КЗ/Выручка — 30%
    "debt_dz_ratio":       0.3,          # ДЗ/Выручка — 30%
}

WEIGHTS = {
    "revenue":          0.22,   # Выручка
    "fixed_assets":     0.12,   # Осн. средства
    "charter_capital":  0.06,   # Уст. капитал
    "net_profit":       0.20,   # Чистая прибыль
    "operating_profit": 0.12,   # Прибыль от продаж
    "pretax_profit":    0.08,   # Прибыль до н/о
    "debt_kz":          0.12,   # Кред. задолж.
    "debt_dz":          0.08,   # Деб. задолж.
}

# ─── Региональные коэффициенты ──────────────────────────────────────────
# Рубежное значение: Москва — 30 млн, Чувашия — 10 млн
# Коэффициент повышения = 30 / 10 = 3.0 → все пороги делятся на этот множитель
# Это даёт ~60% повышение итогового скоринга для Чувашии
REGIONAL_COEFFICIENTS = {
    "чувашская": 3.0,   # 30 млн / 10 млн = 3.0x снижение порогов
}

# ─── Маппинг колонок: имя в Excel → имя в главном листе ─────────────────
COLUMN_MAP = {
    "revenue":          "Выручка",
    "fixed_assets":     "Осн. средства",
    "charter_capital":  "Уст. капитал",
    "net_profit":       "Чистая прибыль",
    "operating_profit": "Прибыль от продаж",
    "pretax_profit":    "прибыль до налогообложения",
    "debt_kz":          "Кред. задолженность",
    "debt_dz":          "Деб. задолженность",
}


def _detect_region(df: pd.DataFrame) -> pd.Series:
    """
    Определяет регион компании по колонке «Адрес» (или аналогичной).
    Возвращает Series с региональным множителем порогов.
    
    Для компаний Чувашской Республики множитель = 3.0 (пороги делятся на 3),
    для остальных = 1.0 (стандартные пороги).
    """
    # Ищем колонку с адресом
    addr_col = next(
        (c for c in df.columns if "адрес" in str(c).lower() or "регион" in str(c).lower()),
        None
    )
    
    if addr_col is None:
        return pd.Series(1.0, index=df.index)
    
    addr = df[addr_col].fillna("").astype(str).str.lower()
    
    multiplier = pd.Series(1.0, index=df.index)
    for region_key, coeff in REGIONAL_COEFFICIENTS.items():
        mask = addr.str.contains(region_key, na=False)
        multiplier = multiplier.where(~mask, coeff)
    
    return multiplier


def score_category_a(df: pd.DataFrame) -> pd.DataFrame:
    """
    Категория A — Финансовое здоровье.

    Вход: df со всеми исходными колонками (полный датасет).
    Выход: тот же df + новые колонки:
      A_score            — балл категории (0-100)
      A_completeness     — полнота данных категории (0-100%)
      A_stop_factor      — 1 если данные достаточны, 0 если стоп
      A_no_revenue_data  — True если финансовых данных нет (для перераспределения весов)
      A_region_coeff     — региональный коэффициент (для диагностики)
    """
    result = df.copy()

    # Определяем региональный множитель порогов
    region_mult = _detect_region(result)

    # Извлекаем сырые значения (приводим к numeric, ошибки → NaN)
    def get_numeric(col_prefix):
        matched_col = next((c for c in result.columns if col_prefix.lower() in str(c).lower()), None)
        if not matched_col:
            return pd.Series(np.nan, index=result.index)
        return pd.to_numeric(result[matched_col], errors="coerce")

    revenue = get_numeric(COLUMN_MAP["revenue"])
    fixed_assets = get_numeric(COLUMN_MAP["fixed_assets"])
    charter = get_numeric(COLUMN_MAP["charter_capital"])
    net_profit = get_numeric(COLUMN_MAP["net_profit"])
    oper_profit = get_numeric(COLUMN_MAP["operating_profit"])
    pretax = get_numeric(COLUMN_MAP["pretax_profit"])
    kz = get_numeric(COLUMN_MAP["debt_kz"])
    dz = get_numeric(COLUMN_MAP["debt_dz"])

    # ─── Определяем отсутствие финансовых данных ─────────────────────────
    # Все ключевые финансовые поля = NaN → данных по финансам действительно нет
    financial_fields = [revenue, fixed_assets, charter, net_profit, oper_profit, pretax, kz, dz]
    all_financial_nan = pd.DataFrame({
        f"f{i}": f.isna() for i, f in enumerate(financial_fields)
    }).all(axis=1)

    # Выручка отсутствует (NaN, а НЕ явный 0)
    revenue_is_missing = revenue.isna()

    # ─── Баллы по прямым показателям ─────────────────────────────────────
    # Формула: ROUND(MAX(0, MIN(1, факт/порог)) * 100, 1)
    # Порог выручки корректируется региональным коэффициентом
    def direct_score(series: pd.Series, threshold: float, apply_region: bool = False) -> pd.Series:
        if apply_region:
            adjusted_threshold = threshold / region_mult
        else:
            adjusted_threshold = threshold
        return np.round(
            np.clip(series.fillna(0) / adjusted_threshold, 0, 1) * 100, 1
        )

    score_revenue = direct_score(revenue, THRESHOLDS["revenue"], apply_region=True)
    score_fixed = direct_score(fixed_assets, THRESHOLDS["fixed_assets"], apply_region=True)
    score_charter = direct_score(charter, THRESHOLDS["charter_capital"])

    # Для прибыли: убыток → 0, иначе линейно до порога
    # Пороги прибыли тоже корректируются региональным коэффициентом
    score_net_profit = direct_score(
        net_profit.clip(lower=0), THRESHOLDS["net_profit"], apply_region=True
    )
    score_oper_profit = direct_score(
        oper_profit.clip(lower=0), THRESHOLDS["operating_profit"], apply_region=True
    )
    score_pretax = direct_score(
        pretax.clip(lower=0), THRESHOLDS["pretax_profit"], apply_region=True
    )

    # ─── Баллы по долговым коэффициентам (инверсия) ──────────────────────
    # Формула: IF(ratio="", 0, ROUND((1 - MIN(1, MAX(0, ratio)/порог)) * 100, 1))
    ratio_kz = kz / revenue.replace(0, np.nan)
    ratio_dz = dz / revenue.replace(0, np.nan)

    score_kz = np.where(
        ratio_kz.isna(),
        0,
        np.round((1 - np.clip(np.clip(ratio_kz, 0, None) / THRESHOLDS["debt_kz_ratio"], 0, 1)) * 100, 1)
    )
    score_dz = np.where(
        ratio_dz.isna(),
        0,
        np.round((1 - np.clip(np.clip(ratio_dz, 0, None) / THRESHOLDS["debt_dz_ratio"], 0, 1)) * 100, 1)
    )

    # ─── Итоговый балл (взвешенная сумма) ────────────────────────────────
    # Формула из Excel: ROUND(N*w1 + O*w2 + ... + U*w8, 1) * стоп-фактор
    total = np.round(
        score_revenue * WEIGHTS["revenue"]
        + score_fixed * WEIGHTS["fixed_assets"]
        + score_charter * WEIGHTS["charter_capital"]
        + score_net_profit * WEIGHTS["net_profit"]
        + score_oper_profit * WEIGHTS["operating_profit"]
        + score_pretax * WEIGHTS["pretax_profit"]
        + score_kz * WEIGHTS["debt_kz"]
        + score_dz * WEIGHTS["debt_dz"],
        1
    )

    # ─── Стоп-фактор ────────────────────────────────────────────────────
    # Формула: IF(Выручка < порог_выручки, 0, 1)
    # Порог выручки тоже корректируется региональным коэффициентом
    adjusted_revenue_threshold = THRESHOLDS["revenue"] / region_mult
    stop_factor = np.where(
        revenue.fillna(0) < adjusted_revenue_threshold, 0, 1
    )

    # Если финансовых данных нет совсем (все NaN), стоп-фактор не применяем —
    # вместо этого помечаем для перераспределения весов
    # no_revenue_data: True когда выручка NaN (не нулевая, а отсутствует)
    no_revenue_data = revenue_is_missing

    # ─── Полнота данных ──────────────────────────────────────────────────
    fields = [revenue, fixed_assets, charter, net_profit, oper_profit, pretax, kz, dz]
    available = sum(~f.isna() for f in fields)
    completeness = np.round(available / len(fields) * 100, 1)

    # Если выручка пустая, но в категории C стоит 0 (из-за неинтересной отрасли),
    # то полнота данных по финансам приравнивается к 100%, так как обогащение не требуется.
    c_score = result.get("C_score", pd.Series(np.nan, index=result.index))
    completeness = np.where(
        revenue.isna() & (c_score == 0),
        100.0,
        completeness
    )

    # ─── Запись результатов ──────────────────────────────────────────────
    result["A_score"] = np.round(total * stop_factor, 1)
    result["A_completeness"] = completeness
    result["A_stop_factor"] = stop_factor
    result["A_no_revenue_data"] = no_revenue_data
    result["A_region_coeff"] = region_mult

    return result
