"""
Result Builder — динамическая сборка итогового результата на основе пресета.
"""
import pandas as pd


def build_result(df: pd.DataFrame, preset: dict, include_source: bool = True) -> pd.DataFrame:
    """
    Формирует итоговый DataFrame для экспорта.
    
    Args:
        df: DataFrame со всеми колонками (исходные + скоринг)
        preset: Конфигурация
        include_source: включить исходные колонки в результат
    """
    # 1. Сбор динамических колонок из пресета
    id_columns = preset.get("id_columns", ["ОГРН", "ИНН", "Краткое наименование"])
    
    score_columns = []
    diag_columns = []
    rename_map = {
        "scoring_total": "Итоговый скоринг",
        "enrichment_priority": "Приоритет обогащения",
        "scoring_segment": "Сегмент",
        "scoring_entropy": "Энтропия",
        "_region_mult": "Региональный множитель"
    }
    
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        cat_name = cat.get("name", cat_id)
        
        score_columns.append(f"{cat_id}_score")
        rename_map[f"{cat_id}_score"] = f"Балл ({cat_id}) {cat_name}"
        
        diag_columns.append(f"{cat_id}_completeness")
        rename_map[f"{cat_id}_completeness"] = f"Полнота данных ({cat_id}) %"
        
        diag_columns.append(f"{cat_id}_stop_factor")
        rename_map[f"{cat_id}_stop_factor"] = f"Стоп-фактор ({cat_id})"
        
    score_columns.extend(["scoring_total", "enrichment_priority", "scoring_segment"])
    diag_columns.append("scoring_entropy")
    diag_columns.append("_region_mult")

    if include_source:
        exclude_list = set(score_columns + diag_columns)
        source_cols = [c for c in df.columns if c not in exclude_list]
        ordered = source_cols + score_columns + diag_columns
    else:
        ordered = id_columns + score_columns

    # Оставляем только существующие колонки
    existing = [c for c in ordered if c in df.columns]
    res_df = df[existing].copy()
    
    # Переименовываем
    res_df.rename(columns=rename_map, inplace=True)
    return res_df
