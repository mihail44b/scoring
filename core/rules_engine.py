"""
Rules Engine — применение весов категорий, стоп-факторов и сегментации.

Веса из config/weights.json, стоп-факторы из категорийных модулей.

Логика перераспределения весов:
  - Если у лида A_no_revenue_data=True (финансовых данных нет) И C_score != 0
    (отрасль нас интересует), то вес категории A перераспределяется
    пропорционально между B, C, D, E.
  - Если C_score == 0, значит компания нас не интересует → итог = 0.
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


def apply_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Рассчитывает итоговый скоринг и сегмент.

    Логика:
      1. Стандартный расчёт: A*wA + B*wB + C*wC + D*wD + E*wE
      2. Если C_score == 0 → итог = 0 (компания нас не интересует)
      3. Если A_no_revenue_data == True И C_score != 0:
         - Вес A перераспределяется пропорционально на B, C, D, E
         - A_score исключается из расчёта
      4. Если любая другая категория == 0 (кроме A при перераспределении) → итог = 0

    Args:
        df: DataFrame с колонками A_score..E_score

    Returns:
        df с колонками: scoring_total, scoring_segment, scoring_weights_mode
    """
    result = df.copy()
    weights = _load_weights()
    segments = _load_segments()

    a = result.get("A_score", pd.Series(0, index=result.index)).fillna(0)
    b = result.get("B_score", pd.Series(0, index=result.index)).fillna(0)
    c = result.get("C_score", pd.Series(0, index=result.index)).fillna(0)
    d = result.get("D_score", pd.Series(0, index=result.index)).fillna(0)
    e = result.get("E_score", pd.Series(0, index=result.index)).fillna(0)

    # Флаг: нет данных по выручке (финансы отсутствуют)
    no_revenue = result.get("A_no_revenue_data", pd.Series(False, index=result.index)).fillna(False)

    # ─── Перераспределение весов ──────────────────────────────────────
    # Условие: выручка отсутствует (NaN) И C_score != 0 (отрасль интересна)
    needs_redistribution = no_revenue & (c != 0)

    # Стандартные веса
    wA = weights["A"]
    wB = weights["B"]
    wC = weights["C"]
    wD = weights["D"]
    wE = weights["E"]

    # Перераспределённые веса (вес A делится пропорционально между B, C, D, E)
    remaining_sum = wB + wC + wD + wE
    redistribute_factor = (remaining_sum + wA) / remaining_sum if remaining_sum > 0 else 1.0

    wB_adj = wB * redistribute_factor
    wC_adj = wC * redistribute_factor
    wD_adj = wD * redistribute_factor
    wE_adj = wE * redistribute_factor

    # ─── Расчёт итогового скоринга ───────────────────────────────────
    # Стандартный расчёт
    weighted_standard = (
        a * wA + b * wB + c * wC + d * wD + e * wE
    )

    # Расчёт с перераспределением (A исключена)
    weighted_redistributed = (
        b * wB_adj + c * wC_adj + d * wD_adj + e * wE_adj
    )

    # Выбираем расчёт в зависимости от флага
    weighted = np.where(needs_redistribution, weighted_redistributed, weighted_standard)

    # ─── Стоп-факторы ────────────────────────────────────────────────
    # Если C_score == 0 → итог = 0 (отрасль нас не интересует — жёсткий стоп)
    c_is_zero = (c == 0)

    # Для стандартного расчёта: если любая категория == 0 → итог = 0
    any_zero_standard = (a == 0) | (b == 0) | (c == 0) | (d == 0) | (e == 0)

    # Для перераспределённого: A не учитывается, остальные проверяем
    any_zero_redistributed = (b == 0) | (c == 0) | (d == 0) | (e == 0)

    # Выбираем условие обнуления
    should_zero = np.where(
        needs_redistribution,
        any_zero_redistributed,
        any_zero_standard
    )

    total = np.where(should_zero, 0, np.round(weighted, 2))
    result["scoring_total"] = total

    # ─── Режим расчёта (для диагностики) ─────────────────────────────
    result["scoring_weights_mode"] = np.where(
        needs_redistribution,
        "перераспределение (без A)",
        "стандартный"
    )

    # ─── Сегментация ─────────────────────────────────────────────────
    def assign_segment(score):
        for seg in segments:
            if score >= seg["min"]:
                return seg["label"]
        return segments[-1]["label"]

    result["scoring_segment"] = pd.Series(total).apply(assign_segment)

    return result
