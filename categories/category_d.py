"""
Категория D — Доступность контакта (участник 4).

Логика 1:1 повторяет формулы из Excel-листа
«Категория D Доступность контакт» (столбцы J–Q):
  J..O — балл по каждому полю (0/100)
  P    — итоговый балл категории
  Q    — стоп-фактор
"""
from __future__ import annotations

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

# ─── Явное сопоставление логических полей с колонками входного файла ────
# Явный маппинг вместо поиска по подстроке: надёжнее, не зависит от
# порядка колонок и не может случайно "перехватить" похожую колонку
# (например "Email" внутри "Доп. Email").
COLUMN_MAP = {
    "phone":    "Телефоны",
    "email":    "Email",
    "website":  "Web-сайты",
    "address":  "Адрес",
    "manager":  "Руководитель",
    "position": "Должность",
}


def _get_series(df: pd.DataFrame, column_name: str) -> pd.Series | None:
    """Возвращает колонку по точному имени (с учётом лишних пробелов)."""
    normalized = {str(c).strip(): c for c in df.columns}
    real_col = normalized.get(column_name.strip())
    return df[real_col] if real_col is not None else None


def _is_present(series: pd.Series | None, n_rows: int) -> np.ndarray:
    """
    Возвращает массив длины n_rows со значениями 100/0.
    Если колонка отсутствует во входном файле — считаем поле
    незаполненным для всех строк (а не роняем расчёт).
    """
    if series is None:
        return np.zeros(n_rows, dtype=float)
    return np.where(
        series.notna() & (series.astype(str).str.strip() != ""),
        100.0, 0.0,
    )


def score_category_d(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    n_rows = len(result)

    s_phone = _is_present(_get_series(result, COLUMN_MAP["phone"]), n_rows)
    s_email = _is_present(_get_series(result, COLUMN_MAP["email"]), n_rows)
    s_web   = _is_present(_get_series(result, COLUMN_MAP["website"]), n_rows)
    s_addr  = _is_present(_get_series(result, COLUMN_MAP["address"]), n_rows)
    s_mgr   = _is_present(_get_series(result, COLUMN_MAP["manager"]), n_rows)
    s_pos   = _is_present(_get_series(result, COLUMN_MAP["position"]), n_rows)

    # Q: стоп-фактор — если пусты и телефон, и email
    stop_factor = np.where((s_phone == 0) & (s_email == 0), 0, 1).astype(int)

    # Взвешенная сумма по весам полей
    weighted = (
        s_phone * D_WEIGHTS["phone"]
        + s_email * D_WEIGHTS["email"]
        + s_web * D_WEIGHTS["website"]
        + s_addr * D_WEIGHTS["address"]
        + s_mgr * D_WEIGHTS["manager"]
        + s_pos * D_WEIGHTS["position"]
    )

    # P: если пусты телефон, сайт, адрес и email одновременно — итог 0,
    # иначе взвешенная сумма, домноженная на стоп-фактор
    no_key_contacts = (s_phone == 0) & (s_web == 0) & (s_addr == 0) & (s_email == 0)
    total = np.where(no_key_contacts, 0.0, weighted) * stop_factor

    # completeness: доля заполненных из 6 полей
    n_fields = len(D_WEIGHTS)
    count_present = (
        (s_phone > 0).astype(int)
        + (s_web > 0).astype(int)
        + (s_email > 0).astype(int)
        + (s_addr > 0).astype(int)
        + (s_mgr > 0).astype(int)
        + (s_pos > 0).astype(int)
    )
    completeness = np.round(count_present / n_fields * 100, 1)

    result["D_score"] = np.round(total, 1)
    result["D_completeness"] = completeness
    result["D_stop_factor"] = stop_factor

    return result