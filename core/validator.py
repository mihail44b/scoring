"""
Валидация входного файла (динамическая).

Проверяет, что загруженный DataFrame содержит обязательные идентификаторы 
и необходимые колонки на основе загруженного пресета.
"""
from dataclasses import dataclass
import pandas as pd


@dataclass
class ValidationResult:
    """Результат проверки DataFrame."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int
    available_categories: list[str]


def validate_input(df: pd.DataFrame, preset: dict) -> ValidationResult:
    """
    Проверяет структуру входного DataFrame на основе пресета.
    """
    errors = []
    warnings = []
    available_categories = []
    
    if df.empty:
        errors.append("Файл не содержит данных (0 строк)")
        return ValidationResult(False, errors, warnings, 0, [])

    existing_cols = list(df.columns)
    columns_lower = [str(c).lower() for c in existing_cols]
    
    # 1. Обязательные колонки (строгий поиск)
    required_cols = preset.get("id_columns", [])
    for req_col in required_cols:
        matches = [c for c in existing_cols if c == req_col]
        if not matches:
            errors.append(f"Отсутствует обязательная колонка: '{req_col}'")
        elif len(matches) > 1:
            warnings.append(f"Найдено несколько колонок '{req_col}' ({len(matches)} шт.). Будет использована первая.")

    # 2. Колонки категорий (по алиасам)
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        cat_name = cat.get("name", cat_id)
        
        missing_in_cat = []
        features = cat.get("features", [])
        
        for feat in features:
            f_name = feat.get("id")
            expected_col = feat.get("name", f_name)
            
            found = False
            expected_lower = str(expected_col).lower()
            matches = [c for c in columns_lower if expected_lower in c]
            if matches:
                found = True
                if len(matches) > 1:
                    warnings.append(f"Категория {cat_name}: найдено несколько колонок для '{expected_col}'. Будет использована первая.")
            
            if not found:
                missing_in_cat.append(expected_col)
                
        if not missing_in_cat:
            available_categories.append(cat_id)
        elif len(missing_in_cat) < len(features):
            available_categories.append(cat_id)
            warnings.append(f"Категория {cat_name}: частичные данные (отсутствуют: {', '.join(missing_in_cat)})")
        else:
            warnings.append(f"Категория {cat_name}: данные отсутствуют полностью")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        row_count=len(df),
        available_categories=available_categories,
    )
