"""
Модули скоринга по категориям.

Каждый модуль содержит функцию score_category_X(df) -> df,
которая принимает полный DataFrame и добавляет колонки с префиксом категории.
"""
from .category_a import score_category_a
from .category_b import score_category_b
from .category_c import score_category_c
from .category_d import score_category_d
from .category_e import score_category_e

__all__ = [
    "score_category_a",
    "score_category_b",
    "score_category_c",
    "score_category_d",
    "score_category_e",
]
