import pandas as pd

from core.validator import ValidationResult, validate_input


def make_validator_preset():
    return {
        "id_columns": ["ИНН"],
        "categories": [
            {
                "id": "A",
                "name": "Финансы",
                "features": [
                    {"id": "revenue", "name": "Выручка"},
                    {"id": "phone", "name": "Телефон"},
                ],
            }
        ],
    }


def test_empty_dataframe_is_invalid():
    result = validate_input(pd.DataFrame(columns=["ИНН"]), make_validator_preset())

    assert isinstance(result, ValidationResult)
    assert result.is_valid is False
    assert result.row_count == 0
    assert "0 строк" in result.errors[0]


def test_missing_required_identifier_is_error():
    df = pd.DataFrame({"Название": ["ООО Тест"]})

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is False
    assert any("ИНН" in error for error in result.errors)
    assert result.row_count == 1


def test_partial_category_is_valid_but_generates_warning():
    df = pd.DataFrame({"ИНН": ["123"], "Выручка за 2025": [100]})

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is True
    assert result.available_categories == ["A"]
    assert any("частичные данные" in warning for warning in result.warnings)
    assert any("Телефон" in warning for warning in result.warnings)


def test_complete_category_is_available_without_partial_warning():
    df = pd.DataFrame(
        {
            "ИНН": ["123"],
            "Выручка": [100],
            "Телефон руководителя": ["+7"],
        }
    )

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is True
    assert result.available_categories == ["A"]
    assert not any("частичные данные" in warning for warning in result.warnings)


def test_completely_missing_category_is_not_available():
    df = pd.DataFrame({"ИНН": ["123"]})

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is True
    assert result.available_categories == []
    assert any("данные отсутствуют полностью" in warning for warning in result.warnings)


def test_required_identifier_search_is_case_sensitive():
    df = pd.DataFrame({"инн": ["123"], "Выручка": [100]})

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is False
    assert any("ИНН" in error for error in result.errors)


def test_duplicate_required_identifier_generates_warning():
    df = pd.DataFrame([["1", "2", 100, "+7"]], columns=["ИНН", "ИНН", "Выручка", "Телефон"])

    result = validate_input(df, make_validator_preset())

    assert result.is_valid is True
    assert any("несколько колонок 'ИНН'" in warning for warning in result.warnings)
