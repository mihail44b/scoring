import numpy as np

from app import _clean_field, _contact_field, _quality_label, _split_multi, extract_region


def test_clean_field_removes_none_nan_and_placeholders():
    assert _clean_field(None) == ""
    assert _clean_field(np.nan) == ""
    assert _clean_field("  Н/Д  ") == ""
    assert _clean_field("  значение  ") == "значение"


def test_split_multi_removes_empty_and_placeholder_parts():
    assert _split_multi("a@example.com, -, b@example.com, Н/Д") == [
        "a@example.com",
        "b@example.com",
    ]
    assert _split_multi("") == []


def test_extract_region_handles_federal_cities():
    assert extract_region("Россия, г. Москва, ул. Тверская") == "г. Москва"
    assert extract_region("г Санкт-Петербург, Невский проспект") == "г. Санкт-Петербург"
    assert extract_region("г. Севастополь") == "г. Севастополь"


def test_extract_region_normalizes_uppercase_region():
    address = "Россия, ЧУВАШСКАЯ РЕСПУБЛИКА, г. Чебоксары"

    assert extract_region(address) == "Чувашская Республика"


def test_extract_region_ignores_municipal_fragment():
    assert extract_region("Россия, городской округ Химки") == "Регион не определён"
    assert extract_region(None) == "Регион не определён"


def test_contact_field_returns_presence_count_and_display_value():
    assert _contact_field("+7, +8") == {
        "present": True,
        "count": 2,
        "display": "+7",
        "extra": 1,
    }
    assert _contact_field("-") == {
        "present": False,
        "count": 0,
        "display": "нет данных",
        "extra": 0,
    }


def test_quality_label_uses_documented_boundaries():
    assert _quality_label(80) == "Высокое"
    assert _quality_label(45) == "Среднее"
    assert _quality_label(44.99) == "Низкое"
