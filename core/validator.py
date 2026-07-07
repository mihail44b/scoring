"""
Валидация входного файла (Pydantic + проверка колонок).

Проверяет, что загруженный Excel/DataFrame содержит все необходимые колонки
для работы категорийных функций.
"""
from dataclasses import dataclass
import pandas as pd

# Обязательные колонки главного листа (ЛИК_дляСкорингаДП)
REQUIRED_COLUMNS = [
    "ОГРН", "ИНН", "Краткое наименование",
]

# Колонки, используемые хотя бы одной категорией
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
    """Результат валидации."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int
    available_categories: list[str]


def validate_input(df: pd.DataFrame) -> ValidationResult:
    """
    Проверяет структуру входного DataFrame.

    Возвращает ValidationResult с информацией о:
    - наличии обязательных колонок
    - доступности данных для каждой категории
    - количестве строк
    """
    errors = []
    warnings = []

    # Проверка обязательных колонок
    existing = set(df.columns)
    for col in REQUIRED_COLUMNS:
        if col not in existing:
            errors.append(f"Отсутствует обязательная колонка: '{col}'")

    # Проверка колонок для каждой категории
    available_categories = []
    columns_lower = [str(c).lower() for c in existing]
    
    for cat, cols in CATEGORY_COLUMNS.items():
        missing = [c for c in cols if not any(c.lower() in col for col in columns_lower)]
        if not missing:
            available_categories.append(cat)
        elif len(missing) < len(cols):
            available_categories.append(cat)
            warnings.append(
                f"Категория {cat}: частичные данные "
                f"(отсутствуют: {', '.join(missing)})"
            )
        else:
            warnings.append(f"Категория {cat}: данные отсутствуют полностью")

    # Проверка количества строк
    if len(df) == 0:
        errors.append("Файл не содержит данных (0 строк)")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        row_count=len(df),
        available_categories=available_categories,
    )
