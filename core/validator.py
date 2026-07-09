"""
Валидация входного файла (проверка наличия необходимых данных).

Проверяет, что загруженный DataFrame содержит обязательные идентификаторы 
(точный поиск) и необходимые колонки для работы категорий (мягкий поиск).
Также отслеживает дубликаты колонок, чтобы предупредить об использовании первой найденной.
"""
from dataclasses import dataclass
import pandas as pd

# Обязательные колонки (строгое совпадение)
REQUIRED_COLUMNS = [
    "ОГРН", "ИНН", "Краткое наименование",
]

# Колонки для скоринга (мягкий поиск по подстроке)
CATEGORY_COLUMNS = {
    "A": [
        "Выручка", "Осн. средства", "Уст. капитал",
        "Чистая прибыль", "Прибыль от продаж",
        "прибыль до налогообложения",
        "Кред. задолженность", "Деб. задолженность",
    ],
    "B": ["Регистрация", "РМСП", "кол-во сотрудников", "Запасы"],
    "C": ["ОКВЭД", "Налоговый режим"],
    "D": ["Телефоны", "Web-сайты", "Email", "Адрес", "Руководитель", "Должность"],
    "E": ["Ликвидация", "ОКФС", "ОКОПФ", "ИНН руководителя"],
}


@dataclass
class ValidationResult:
    """Результат проверки DataFrame."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int
    available_categories: list[str]


def validate_input(df: pd.DataFrame) -> ValidationResult:
    """
    Проверяет структуру входного DataFrame перед запуском скоринга.
    
    Возвращает ValidationResult со списками ошибок (errors) и 
    предупреждений (warnings). Если len(errors) > 0, файл не валиден.
    """
    errors = []
    warnings = []
    available_categories = []
    
    # ─── 1. Проверка на пустоту ──────────────────────────────────────
    if df.empty:
        errors.append("Файл не содержит данных (0 строк)")
        return ValidationResult(False, errors, warnings, 0, [])

    # ─── 2. Проверка обязательных колонок (строгий поиск) ────────────
    # Здесь нужно точное совпадение, чтобы не спутать "ИНН" с "ИНН руководителя"
    existing_cols = list(df.columns)
    
    for req_col in REQUIRED_COLUMNS:
        # Считаем точные совпадения (в Excel могут быть две колонки с одним именем)
        matches = [c for c in existing_cols if c == req_col]
        
        if not matches:
            errors.append(f"Отсутствует обязательная колонка: '{req_col}'")
        elif len(matches) > 1:
            warnings.append(f"Найдено несколько колонок '{req_col}' ({len(matches)} шт.). Будет использована первая.")

    # ─── 3. Проверка колонок категорий (мягкий поиск) ────────────────
    columns_lower = [str(c).lower() for c in existing_cols]
    
    for cat, cols in CATEGORY_COLUMNS.items():
        missing_in_cat = []
        
        for expected_col in cols:
            expected_lower = expected_col.lower()
            # Ищем все колонки, содержащие искомую подстроку (например, "Выручка (2025)")
            matches = [c for c in columns_lower if expected_lower in c]
            
            if not matches:
                missing_in_cat.append(expected_col)
            elif len(matches) > 1:
                # Если нашли несколько подходящих (например, "Телефоны (1)", "Телефоны (2)")
                warnings.append(f"Категория {cat}: найдено несколько колонок для '{expected_col}'. Будет использована первая.")
                
        # Оценка доступности категории
        if not missing_in_cat:
            available_categories.append(cat)
        elif len(missing_in_cat) < len(cols):
            available_categories.append(cat)
            warnings.append(f"Категория {cat}: частичные данные (отсутствуют: {', '.join(missing_in_cat)})")
        else:
            warnings.append(f"Категория {cat}: данные отсутствуют полностью")

    # ─── 4. Формирование результата ──────────────────────────────────
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        row_count=len(df),
        available_categories=available_categories,
    )
