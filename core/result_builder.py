"""
Result Builder — сборка итогового результата.

Определяет порядок и состав колонок в итоговом выходном файле.
"""
import pandas as pd


# Колонки идентификации
ID_COLUMNS = ["ОГРН", "ИНН", "Краткое наименование"]

# Колонки скоринга (порядок как в Excel)
SCORE_COLUMNS = [
    "A_score", "B_score", "C_score", "D_score", "E_score",
    "scoring_total", "scoring_segment",
]

# Доп. диагностические колонки
DIAG_COLUMNS = [
    "A_completeness", "A_stop_factor",
    "B_completeness", "B_stop_factor",
    "C_completeness", "C_stop_factor", "C_status",
    "D_completeness", "D_stop_factor",
    "E_completeness", "E_stop_factor",
]

# Перевод колонок на русский язык для итогового файла
RENAME_MAP = {
    "A_score": "Балл (A) Фин. здоровье",
    "A_completeness": "Полнота данных (A) %",
    "A_stop_factor": "Стоп-фактор (A)",
    "B_score": "Балл (B) Масштаб",
    "B_completeness": "Полнота данных (B) %",
    "B_stop_factor": "Стоп-фактор (B)",
    "C_score": "Балл (C) Отрасль",
    "C_completeness": "Полнота данных (C) %",
    "C_stop_factor": "Стоп-фактор (C)",
    "C_status": "Статус (C)",
    "D_score": "Балл (D) Контакты",
    "D_completeness": "Полнота данных (D) %",
    "D_stop_factor": "Стоп-фактор (D)",
    "E_score": "Балл (E) Юр. статус",
    "E_completeness": "Полнота данных (E) %",
    "E_stop_factor": "Стоп-фактор (E)",
    "scoring_total": "Итоговый скоринг",
    "scoring_segment": "Сегмент",
}


def build_result(df: pd.DataFrame, include_source: bool = True) -> pd.DataFrame:
    """
    Формирует итоговый DataFrame для экспорта.

    Args:
        df: DataFrame со всеми колонками (исходные + скоринг)
        include_source: включить исходные колонки в результат

    Returns:
        DataFrame с упорядоченными колонками
    """
    if include_source:
        # Все исходные + скоринг + диагностика
        source_cols = [c for c in df.columns if c not in SCORE_COLUMNS + DIAG_COLUMNS]
        ordered = source_cols + SCORE_COLUMNS + DIAG_COLUMNS
    else:
        ordered = ID_COLUMNS + SCORE_COLUMNS

    # Оставляем только существующие колонки
    existing = [c for c in ordered if c in df.columns]
    res_df = df[existing].copy()
    
    # Переименовываем в русские названия
    res_df.rename(columns=RENAME_MAP, inplace=True)
    return res_df
