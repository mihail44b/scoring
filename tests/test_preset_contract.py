import pytest


def test_current_preset_has_valid_category_weights(actual_preset):
    category_weights = [category["weight"] for category in actual_preset["categories"]]

    assert sum(category_weights) == pytest.approx(1.0)


def test_current_preset_has_valid_feature_weights(actual_preset):
    for category in actual_preset["categories"]:
        feature_weights = [feature["weight"] for feature in category.get("features", [])]
        if feature_weights:
            assert sum(feature_weights) == pytest.approx(1.0), category["id"]


def test_current_preset_has_unique_feature_ids_and_known_method_types(actual_preset):
    allowed_methods = {
        "log_scale",
        "debt_ratio",
        "percentile_rank",
        "categorical_mapping",
        "okved_mapping",
        "tax_mapping",
        "log_score_simple",
        "binary_presence",
    }

    for category in actual_preset["categories"]:
        feature_ids = [feature["id"] for feature in category.get("features", [])]
        assert len(feature_ids) == len(set(feature_ids)), category["id"]
        for feature in category.get("features", []):
            assert feature["scoring_method"]["type"] in allowed_methods


def test_current_preset_stop_factor_references_are_declared_features(actual_preset):
    for category in actual_preset["categories"]:
        feature_ids = {feature["id"] for feature in category.get("features", [])}
        for stop_factor in category.get("stop_factors", []):
            if stop_factor.get("feature"):
                assert stop_factor["feature"] in feature_ids
            for feature_id in stop_factor.get("features", []) or []:
                assert feature_id in feature_ids


def test_segment_thresholds_are_in_descending_order(actual_preset):
    thresholds = [segment["min_score"] for segment in actual_preset["segments"].values()]

    assert thresholds == sorted(thresholds, reverse=True)


def test_current_preset_passes_pydantic_schema(actual_preset):
    # Импортируем app только в этом тесте: остальные контрактные проверки
    # могут выполняться независимо от FastAPI.
    from app import PresetSchema

    PresetSchema(**actual_preset)
