import pandas as pd
import pytest

from core.engine import (
    ColumnCache,
    _extract_okved_class,
    _get_regional_coeff,
    calculate_scoring,
)


def make_feature(feature_id, name, method_type, params=None, weight=1.0):
    scoring_method = {"type": method_type}
    if params is not None:
        scoring_method["params"] = params
    return {
        "id": feature_id,
        "name": name,
        "weight": weight,
        "scoring_method": scoring_method,
    }


def make_preset(
    features,
    *,
    category_id="A",
    category_weight=1.0,
    stop_factors=None,
    category_modifiers=None,
    diagnostic_columns=None,
    regional_coefficients=None,
    segments=None,
):
    category = {
        "id": category_id,
        "name": category_id,
        "weight": category_weight,
        "features": features,
        "stop_factors": stop_factors or [],
    }
    if category_modifiers is not None:
        category["category_modifiers"] = category_modifiers
    if diagnostic_columns is not None:
        category["diagnostic_columns"] = diagnostic_columns

    preset = {
        "categories": [category],
        "segments": segments or {},
        "enrichment_weights": {
            "score_weight": 0.6,
            "entropy_weight": 0.4,
        },
    }
    if regional_coefficients is not None:
        preset["regional_coefficients"] = regional_coefficients
    return preset


def test_column_cache_finds_exact_partial_and_missing_columns():
    cache = ColumnCache(["Выручка (2025)", "АДРЕС"])

    assert cache.find(["адрес"]) == "АДРЕС"
    assert cache.find(["выручка"]) == "Выручка (2025)"
    assert cache.find(["отсутствует"]) is None

    # Повторный запрос возвращает закэшированный результат.
    assert cache.find(["выручка"]) == "Выручка (2025)"
    assert cache.cache[("выручка",)] == "Выручка (2025)"


def test_regional_coefficients_preserve_dataframe_index():
    df = pd.DataFrame(
        {"Адрес": ["Чувашия", "Москва", None]},
        index=[10, 20, 30],
    )
    cache = ColumnCache(df.columns)
    preset = {
        "regional_coefficients": {
            "keywords": ["адрес"],
            "rules": {"чуваш": 3},
        }
    }

    result = _get_regional_coeff(df, preset, cache)

    assert result.index.tolist() == [10, 20, 30]
    assert result.tolist() == [3.0, 1.0, 1.0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (pd.NA, ""),
        ("", ""),
        ("1.23", "01"),
        ("62.01", "62"),
        ("08", "08"),
        (" 7 ", "07"),
    ],
)
def test_extract_okved_class(value, expected):
    assert _extract_okved_class(value) == expected


def test_log_scale_respects_threshold_and_formula():
    df = pd.DataFrame({"Выручка": [99, 100, 200]})
    preset = make_preset(
        [
            make_feature(
                "revenue",
                "Выручка",
                "log_scale",
                {"threshold": 100, "scale": 20},
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([0.0, 0.0, 23.1])


def test_profit_log_scale_clips_negative_values():
    df = pd.DataFrame({"Чистая прибыль": [-500, 100, 400]})
    preset = make_preset(
        [
            make_feature(
                "net_profit",
                "Чистая прибыль",
                "log_scale",
                {"threshold": 100, "scale": 20},
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result.loc[0, "A_score"] == 0
    assert result.loc[1, "A_score"] == 0
    assert result.loc[2, "A_score"] > 0


def test_log_scale_can_apply_regional_coefficient():
    df = pd.DataFrame(
        {
            "Адрес": ["Чувашия", "Москва"],
            "Выручка": [100, 100],
        }
    )
    preset = make_preset(
        [
            make_feature(
                "revenue",
                "Выручка",
                "log_scale",
                {
                    "threshold": 100,
                    "scale": 20,
                    "apply_regional_coeff": True,
                },
            )
        ],
        regional_coefficients={
            "keywords": ["адрес"],
            "rules": {"чуваш": 3},
        },
    )

    result = calculate_scoring(df, preset)

    assert result["_region_mult"].tolist() == [3.0, 1.0]
    assert result.loc[0, "A_score"] > 0
    assert result.loc[1, "A_score"] == 0


def test_string_false_regional_flag_is_not_treated_as_true():
    """Регрессионный тест для текущего JSON-пресета."""
    df = pd.DataFrame({"Адрес": ["Чувашия"], "Выручка": [100]})
    preset = make_preset(
        [
            make_feature(
                "revenue",
                "Выручка",
                "log_scale",
                {
                    "threshold": 100,
                    "scale": 20,
                    # Так записано в legacy_default.json.
                    "apply_regional_coeff": "false",
                },
            )
        ],
        regional_coefficients={
            "keywords": ["адрес"],
            "rules": {"чуваш": 3},
        },
    )

    result = calculate_scoring(df, preset)

    # Сейчас этот тест падает: непустая строка "false" считается True.
    assert result.loc[0, "A_score"] == pytest.approx(0.0)


def test_debt_ratio_uses_revenue_feature_and_handles_missing_values():
    df = pd.DataFrame(
        {
            "Выручка": [100, 100, 100, 0],
            "Кред. задолженность": [0, 30, 60, 10],
        }
    )
    preset = make_preset(
        [
            make_feature(
                "revenue",
                "Выручка",
                "binary_presence",
                {"present": 100, "absent": 0},
                weight=0,
            ),
            make_feature(
                "debt_kz",
                "Кред. задолженность",
                "debt_ratio",
                {"threshold": 0.3, "revenue_feature": "revenue"},
            ),
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([100.0, 0.0, 0.0, 0.0])


def test_percentile_rank_scores_oldest_date_higher_and_missing_as_zero():
    df = pd.DataFrame(
        {"Регистрация": ["2020-01-01", "2022-01-01", "2021-01-01", None]}
    )
    preset = make_preset(
        [make_feature("registration", "Регистрация", "percentile_rank")]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([100.0, 0.0, 50.0, 0.0])
    assert result["A_completeness"].tolist() == pytest.approx([100.0, 100.0, 100.0, 0.0])


def test_categorical_mapping_uses_mapping_default_and_empty_score():
    df = pd.DataFrame(
        {"РМСП": ["Микропредприятие", "", "Неизвестное", None]}
    )
    preset = make_preset(
        [
            make_feature(
                "rmsp",
                "РМСП",
                "categorical_mapping",
                {
                    "mapping": {"Микропредприятие": 25},
                    "default_score": 50,
                    "empty_score": 100,
                },
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([25.0, 100.0, 50.0, 100.0])
    # При empty_score=100 движок считает пустые значения допустимо заполненными.
    assert result["A_completeness"].tolist() == pytest.approx([100.0] * 4)


def test_okved_mapping_extracts_class_before_lookup():
    df = pd.DataFrame({"ОКВЭД": ["10.11", "84.1", "99.99", None]})
    preset = make_preset(
        [
            make_feature(
                "okved",
                "ОКВЭД",
                "okved_mapping",
                {
                    "mapping": {"10": 100, "84": 0},
                    "default_score": 25,
                },
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([100.0, 0.0, 25.0, 25.0])


def test_tax_mapping_normalizes_osno_alias_and_case():
    df = pd.DataFrame(
        {"Налоговый режим": ["ОСНО", "осн", "УСН", "ЕСХН", "Неизвестно", None]}
    )
    preset = make_preset(
        [
            make_feature(
                "tax_regime",
                "Налоговый режим",
                "tax_mapping",
                {
                    "mapping": {"ОСН": 100, "УСН": 50, "ЕСХН": 40},
                    "default_score": 0,
                },
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([100.0, 100.0, 50.0, 40.0, 0.0, 0.0])


def test_log_score_simple_uses_logarithmic_rank_and_special_one():
    df = pd.DataFrame({"Сотрудники": [1, 10, 100, 0, None]})
    preset = make_preset(
        [
            make_feature(
                "employees",
                "Сотрудники",
                "log_score_simple",
                {"cap": 100, "special_one": 1},
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([1.0, 50.0, 100.0, 0.0, 0.0])


def test_binary_presence_distinguishes_empty_and_non_empty_values():
    df = pd.DataFrame({"Телефон": ["123", "  ", "", None]})
    preset = make_preset(
        [
            make_feature(
                "phone",
                "Телефон",
                "binary_presence",
                {"present": 100, "absent": 0},
            )
        ]
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([100.0, 0.0, 0.0, 0.0])


def test_numeric_stop_factor_uses_feature_threshold():
    df = pd.DataFrame({"Выручка": [99, 100, 101]})
    preset = make_preset(
        [
            make_feature(
                "revenue",
                "Выручка",
                "log_scale",
                {"threshold": 100, "scale": 20},
            )
        ],
        stop_factors=[
            {
                "type": "numeric_condition",
                "feature": "revenue",
                "operator": "<",
            }
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["A_stop_factor"].tolist() == [0, 1, 1]


def test_exact_value_stop_factor_zeroes_matching_value():
    df = pd.DataFrame({"Риск": [0, 1, None]})
    preset = make_preset(
        [
            make_feature(
                "risk",
                "Риск",
                "binary_presence",
                {"present": 100, "absent": 0},
            )
        ],
        stop_factors=[
            {"type": "exact_value", "feature": "risk", "value": 0}
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["A_stop_factor"].tolist() == [0, 1, 1]


def test_missing_all_stop_factor_requires_at_least_one_value():
    df = pd.DataFrame({"F1": ["", "x"], "F2": [None, None]})
    preset = make_preset(
        [
            make_feature("f1", "F1", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
            make_feature("f2", "F2", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
        ],
        stop_factors=[
            {"type": "missing_all", "features": ["f1", "f2"]}
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["A_stop_factor"].tolist() == [0, 1]


def test_categorical_in_stop_factor_uses_mapping_score():
    df = pd.DataFrame({"ОКВЭД": ["84.1", "10.1"]})
    preset = make_preset(
        [
            make_feature(
                "okved",
                "ОКВЭД",
                "okved_mapping",
                {"mapping": {"84": 0, "10": 100}, "default_score": 0},
            )
        ],
        stop_factors=[
            {
                "type": "categorical_in",
                "feature": "okved",
                "values_with_score": 0,
            }
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["A_stop_factor"].tolist() == [0, 1]


def test_present_stop_factor_marks_non_empty_liquidation_field():
    df = pd.DataFrame({"Ликвидация": [None, "В процессе"]})
    preset = make_preset(
        [
            make_feature(
                "liquidation",
                "Ликвидация",
                "binary_presence",
                {"present": 0, "absent": 100},
            )
        ],
        stop_factors=[{"type": "present", "feature": "liquidation"}],
    )

    result = calculate_scoring(df, preset)

    assert result["A_stop_factor"].tolist() == [1, 0]


def test_zero_if_missing_all_category_modifier_zeroes_only_empty_rows():
    df = pd.DataFrame({"F1": [None, "yes"], "F2": [None, None]})
    preset = make_preset(
        [
            make_feature("f1", "F1", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
            make_feature("f2", "F2", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
        ],
        category_modifiers=[
            {"type": "zero_if_missing_all", "features": ["f1", "f2"]}
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["A_score"].tolist() == pytest.approx([0.0, 50.0])


def test_contact_status_diagnostic_reports_all_four_states():
    df = pd.DataFrame(
        {
            "Телефон": ["123", "", "123", ""],
            "Email": ["", "a@example.com", "a@example.com", ""],
        }
    )
    preset = make_preset(
        [
            make_feature("phone", "Телефон", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
            make_feature("email", "Email", "binary_presence", {"present": 100, "absent": 0}, weight=0.5),
        ],
        category_id="D",
        diagnostic_columns=[
            {
                "id": "contact_status",
                "name": "Статус контактов",
                "type": "contact_status",
                "features": ["phone", "email"],
                "values": {
                    "both": "телефон и email",
                    "phone_only": "только телефон",
                    "email_only": "только email",
                    "none": "нет контактов",
                },
            }
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["D_contact_status"].tolist() == [
        "только телефон",
        "только email",
        "телефон и email",
        "нет контактов",
    ]


def test_categorical_unknown_diagnostic_reports_unknown_codes():
    df = pd.DataFrame(
        {
            "ОКФС": ["16", "999"],
            "ОКОПФ": ["10000", "99999"],
        }
    )
    preset = make_preset(
        [
            make_feature(
                "okfs",
                "ОКФС",
                "categorical_mapping",
                {"mapping": {"16": 100}, "default_score": 50},
                weight=0.5,
            ),
            make_feature(
                "okopf",
                "ОКОПФ",
                "categorical_mapping",
                {"mapping": {"10000": 100}, "default_score": 50},
                weight=0.5,
            ),
        ],
        category_id="E",
        diagnostic_columns=[
            {
                "id": "status",
                "name": "Статус",
                "type": "categorical_unknown",
                "features": ["okfs", "okopf"],
                "values": {"none": "OK"},
            }
        ],
    )

    result = calculate_scoring(df, preset)

    assert result["E_status"].tolist() == [
        "OK",
        "UNKNOWN_OKFS, UNKNOWN_OKOPF",
    ]


def test_total_score_segment_completeness_and_priority():
    df = pd.DataFrame({"A data": ["yes", "yes"], "D data": ["yes", ""]})
    preset = {
        "categories": [
            {
                "id": "A",
                "name": "A",
                "weight": 0.5,
                "features": [
                    make_feature("a", "A data", "binary_presence", {"present": 100, "absent": 0})
                ],
                "stop_factors": [],
            },
            {
                "id": "D",
                "name": "D",
                "weight": 0.5,
                "features": [
                    make_feature("d", "D data", "binary_presence", {"present": 100, "absent": 0})
                ],
                "stop_factors": [],
            },
        ],
        "segments": {
            "hot": {"min_score": 70, "label": "Горячий"},
            "warm": {"min_score": 40, "label": "Тёплый"},
            "cold": {"min_score": 1, "label": "Холодный"},
        },
        "enrichment_weights": {"score_weight": 0.6, "entropy_weight": 0.4},
    }

    result = calculate_scoring(df, preset)

    assert result["scoring_total"].tolist() == pytest.approx([100.0, 0.0])
    assert result.loc[0, "scoring_segment"] == "Горячий"
    assert pd.isna(result.loc[1, "scoring_segment"])
    assert result["scoring_completeness"].tolist() == pytest.approx([100.0, 50.0])
    assert result["enrichment_priority"].tolist() == pytest.approx([60.0, 0.0])
