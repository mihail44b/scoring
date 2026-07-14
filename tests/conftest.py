import io
import json
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def project_root() -> Path:
    """Корень проекта, если tests/ скопирован в scoring/tests/."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def actual_preset(project_root: Path) -> dict:
    """Текущий рабочий JSON-пресет проекта."""
    preset_path = project_root / "config" / "presets" / "legacy_default.json"
    return json.loads(preset_path.read_text(encoding="utf-8"))


@pytest.fixture
def complete_input_df() -> pd.DataFrame:
    """Минимальная полностью структурированная запись для API-тестов."""
    return pd.DataFrame(
        [
            {
                "ОГРН": "1020000000001",
                "ИНН": "2123456789",
                "Краткое наименование": "ООО Тест",
                "Выручка": 500_000_000,
                "Осн. средства": 100_000_000,
                "Уст. капитал": 10_000_000,
                "Чистая прибыль": 50_000_000,
                "Прибыль от продаж": 40_000_000,
                "прибыль до налогообложения": 45_000_000,
                "Кред. задолженность": 10_000_000,
                "Деб. задолженность": 5_000_000,
                "Регистрация": "2020-01-01",
                "РМСП": "Среднее предприятие",
                "кол-во сотрудников": 100,
                "Запасы": 50_000_000,
                "ОКВЭД": "10.11",
                "Налоговый режим": "ОСН",
                "Телефоны": "+7 900 000-00-00",
                "Email": "test@example.com",
                "Web-сайты": "https://example.com",
                "Адрес": "Чувашская Республика, г. Чебоксары",
                "Руководитель": "Иванов Иван Иванович",
                "Должность": "Генеральный директор",
                "Ликвидация": None,
                "ОКФС": "16",
                "ОКОПФ": "10000",
                "ИНН руководителя": "212345678900",
            }
        ]
    )


@pytest.fixture
def excel_bytes(complete_input_df: pd.DataFrame) -> bytes:
    """Excel-файл в памяти; тестам не нужен отдельный бинарный fixture."""
    buffer = io.BytesIO()
    complete_input_df.to_excel(buffer, index=False)
    return buffer.getvalue()
