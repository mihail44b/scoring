import pandas as pd

from core.result_builder import build_result


def make_preset():
    return {
        "id_columns": ["ИНН"],
        "categories": [
            {
                "id": "A",
                "name": "Финансы",
                "features": [],
                "diagnostic_columns": [
                    {
                        "id": "status",
                        "name": "Статус",
                        "type": "contact_status",
                        "features": ["phone", "email"],
                    }
                ],
            }
        ],
    }


def make_scored_df():
    return pd.DataFrame(
        {
            "ИНН": ["123"],
            "Исходное поле": ["сохранить"],
            "A_score": [80.0],
            "A_completeness": [100.0],
            "A_stop_factor": [1.0],
            "A_status": ["OK"],
            "_region_mult": [1.0],
            "scoring_entropy": [10.0],
            "scoring_completeness": [90.0],
            "scoring_total": [70.0],
            "scoring_segment": ["Горячий"],
            "enrichment_priority": [46.0],
        }
    )


def test_build_result_keeps_source_columns_and_renames_generated_columns():
    result = build_result(make_scored_df(), make_preset(), include_source=True)

    assert result.columns.tolist() == [
        "ИНН",
        "Исходное поле",
        "Балл категории A",
        "Качество данных (%)",
        "Итоговый скоринг",
        "Сегмент",
        "Приоритет обогащения",
    ]
    assert result.loc[0, "Исходное поле"] == "сохранить"
    assert result.loc[0, "Балл категории A"] == 80.0
    assert "A_status" not in result.columns
    assert "_region_mult" not in result.columns


def test_build_result_without_source_keeps_only_identifier_and_targets():
    result = build_result(make_scored_df(), make_preset(), include_source=False)

    assert result.columns.tolist() == [
        "ИНН",
        "Балл категории A",
        "Качество данных (%)",
        "Итоговый скоринг",
        "Сегмент",
        "Приоритет обогащения",
    ]
    assert "Исходное поле" not in result.columns
