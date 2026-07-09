"""
Категория D — Доступность контакта (участник 4).

У категории D больше НЕТ стоп-фактора — отсутствие контактов
(телефона/email) не отсеивает лид, а просто даёт низкий балл по
категории. Вместо стоп-фактора считаем диагностическую колонку
D_contact_status — есть ли у клиента телефон и/или email.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

# ─── Веса категории D ────────────────────────────────────────────────────
D_WEIGHTS = {
    "phone":    0.25,
    "email":    0.25,
    "website":  0.20,
    "address":  0.15,
    "manager":  0.10,
    "position": 0.05,
}

# ─── Явное сопоставление логических полей с колонками входного файла ────
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
    """Возвращает массив длины n_rows со значениями 100/0."""
    if series is None:
        return np.zeros(n_rows, dtype=float)
    return np.where(
        series.notna() & (series.astype(str).str.strip() != ""),
        100.0, 0.0,
    )


def _contact_status(has_phone: np.ndarray, has_email: np.ndarray) -> np.ndarray:
    """
    Диагностическая колонка наличия ключевых каналов связи.
    Заменяет прежний стоп-фактор — используется для ручной фильтрации/анализа,
    но не влияет на сам балл категории.
    """
    status = np.full(has_phone.shape, "нет контактов", dtype=object)
    both = (has_phone > 0) & (has_email > 0)
    phone_only = (has_phone > 0) & (has_email == 0)
    email_only = (has_phone == 0) & (has_email > 0)

    status[phone_only] = "только телефон"
    status[email_only] = "только email"
    status[both] = "телефон и email"
    return status


def score_category_d(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    n_rows = len(result)

    s_phone = _is_present(_get_series(result, COLUMN_MAP["phone"]), n_rows)
    s_email = _is_present(_get_series(result, COLUMN_MAP["email"]), n_rows)
    s_web   = _is_present(_get_series(result, COLUMN_MAP["website"]), n_rows)
    s_addr  = _is_present(_get_series(result, COLUMN_MAP["address"]), n_rows)
    s_mgr   = _is_present(_get_series(result, COLUMN_MAP["manager"]), n_rows)
    s_pos   = _is_present(_get_series(result, COLUMN_MAP["position"]), n_rows)

    # Итоговый балл — просто взвешенная сумма, без стоп-фактора.
    # Если все поля пусты, сумма и так естественным образом равна 0.
    total = (
        s_phone * D_WEIGHTS["phone"]
        + s_email * D_WEIGHTS["email"]
        + s_web * D_WEIGHTS["website"]
        + s_addr * D_WEIGHTS["address"]
        + s_mgr * D_WEIGHTS["manager"]
        + s_pos * D_WEIGHTS["position"]
    )

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
    result["D_contact_status"] = _contact_status(s_phone, s_email)

    return result