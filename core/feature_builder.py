"""
Feature Builder — вызывает все категорийные функции по очереди.

Собирает единый DataFrame с баллами всех категорий.
"""
import pandas as pd
from categories.category_a import score_category_a
from categories.category_b import score_category_b
from categories.category_c import score_category_c
from categories.category_d import score_category_d
from categories.category_e import score_category_e


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Последовательно вызывает все 5 категорийных функций,
    каждая добавляет свои колонки с префиксом (A_, B_, C_, D_, E_).

    Args:
        df: входной DataFrame с сырыми данными

    Returns:
        df с добавленными колонками всех категорий
    """
    df = score_category_a(df)
    df = score_category_b(df)
    df = score_category_c(df)
    df = score_category_d(df)
    df = score_category_e(df)
    return df
