import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    import app as app_module

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setattr(app_module, "TEMP_DIR", str(temp_dir))

    with TestClient(app_module.app) as client:
        yield client


def upload(data: bytes, filename: str = "sample.xlsx"):
    return {
        "file": (
            filename,
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


def dataframe_to_xlsx(dataframe: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    dataframe.to_excel(buffer, index=False)
    return buffer.getvalue()


def test_health_endpoint(api_client):
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "2.0.0"}


def test_html_pages_are_available(api_client):
    assert api_client.get("/").status_code == 200
    assert api_client.get("/settings").status_code == 200


def test_score_rejects_non_excel_extension(api_client, excel_bytes):
    response = api_client.post("/score", files=upload(excel_bytes, "sample.csv"))

    assert response.status_code == 400
    assert "xlsx" in response.json()["detail"]


def test_preview_returns_scored_rows_for_valid_excel(api_client, excel_bytes):
    response = api_client.post("/score/preview", files=upload(excel_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["validation"]["is_valid"] is True
    assert body["validation"]["row_count"] == 1
    assert len(body["preview"]) == 1
    assert "scoring_total" in body["preview"][0]


def test_preview_rejects_invalid_input_structure(api_client):
    invalid_df = pd.DataFrame({"ИНН": ["123"]})
    invalid_xlsx = dataframe_to_xlsx(invalid_df)

    response = api_client.post("/score/preview", files=upload(invalid_xlsx))

    # Эндпоинт должен вести себя так же, как /score и /api/score/full.
    # На текущем коде этот тест выявляет отсутствие проверки is_valid.
    assert response.status_code == 422


def test_score_returns_xlsx_for_valid_input(api_client, excel_bytes):
    response = api_client.post("/score", files=upload(excel_bytes))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content[:2] == b"PK"


def test_full_score_and_download_flow(api_client, excel_bytes):
    response = api_client.post("/api/score/full", files=upload(excel_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["validation"]["is_valid"] is True
    assert body["stats"]["total"] == 1
    assert len(body["records"]) == 1
    assert body["file_id"]

    download = api_client.get(
        f"/api/score/download/{body['file_id']}",
        params={"filename": "результат.xlsx"},
    )

    assert download.status_code == 200
    assert download.content[:2] == b"PK"
    assert "filename*=UTF-8''" in download.headers["content-disposition"]


def test_full_score_returns_validation_error_for_invalid_input(api_client):
    invalid_df = pd.DataFrame({"ИНН": ["123"]})
    invalid_xlsx = dataframe_to_xlsx(invalid_df)

    response = api_client.post("/api/score/full", files=upload(invalid_xlsx))

    assert response.status_code == 422
    assert response.json()["errors"]


def test_settings_get_returns_available_json_configs(api_client):
    response = api_client.get("/api/settings/configs")

    assert response.status_code == 200
    configs = response.json()
    assert "legacy_default.json" in configs
    assert "categories" in configs["legacy_default.json"]


def test_settings_rejects_path_like_filename(api_client):
    response = api_client.post(
        "/api/settings/configs",
        json={"../outside.json": {}},
    )

    assert response.status_code == 400
    assert "Недопустимое имя файла" in response.json()["detail"]


def test_settings_rejects_invalid_preset_structure(api_client):
    response = api_client.post(
        "/api/settings/configs",
        json={"test.json": {"categories": []}},
    )

    assert response.status_code == 422
    assert "Ошибка структуры" in response.json()["detail"]
