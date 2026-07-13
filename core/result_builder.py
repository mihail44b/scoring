import pandas as pd

def build_result(df: pd.DataFrame, preset: dict, include_source: bool = True) -> pd.DataFrame:
    """
    Формирует итоговый DataFrame для экспорта.
    """
    id_columns = preset.get("id_columns", ["ОГРН", "ИНН", "Краткое наименование"])
    
    # Собираем все сгенерированные технические колонки, чтобы отфильтровать их из исходных
    all_generated_cols = [
        "scoring_total", "enrichment_priority", "scoring_segment", 
        "scoring_entropy", "_region_mult", "scoring_completeness"
    ]
    
    cat_scores = []
    
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        cat_scores.append(f"{cat_id}_score")
        all_generated_cols.extend([
            f"{cat_id}_score",
            f"{cat_id}_completeness",
            f"{cat_id}_stop_factor"
        ])
        for diag in cat.get("diagnostic_columns", []):
            all_generated_cols.append(f"{cat_id}_{diag['id']}")
            
    exclude_list = set(all_generated_cols)
    
    # Колонки, которые пойдут в финальный отчет в нужном порядке
    target_columns = cat_scores + ["scoring_completeness", "scoring_total", "scoring_segment", "enrichment_priority"]
    
    rename_map = {
        "scoring_completeness": "Качество данных (%)",
        "scoring_total": "Итоговый скоринг",
        "scoring_segment": "Сегмент",
        "enrichment_priority": "Приоритет обогащения"
    }
    
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        rename_map[f"{cat_id}_score"] = f"Балл категории {cat_id}"

    if include_source:
        source_cols = [c for c in df.columns if c not in exclude_list]
        ordered = source_cols + target_columns
    else:
        ordered = id_columns + target_columns

    # Оставляем только существующие колонки
    existing = [c for c in ordered if c in df.columns]
    res_df = df[existing].copy()
    
    # Переименовываем
    res_df.rename(columns=rename_map, inplace=True)
    return res_df
