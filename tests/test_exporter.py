import io

import pandas as pd

from core.exporter import export_to_excel


def test_export_to_excel_returns_readable_xlsx_bytes():
    source = pd.DataFrame({"ИНН": ["123"], "Итоговый скоринг": [75.5]})

    data = export_to_excel(source)

    assert isinstance(data, bytes)
    assert data[:2] == b"PK"  # XLSX — ZIP-контейнер.

    restored = pd.read_excel(io.BytesIO(data), sheet_name="Скоринг")
    assert restored.columns.tolist() == source.columns.tolist()
    # Excel может вернуть числовой идентификатор как int вместо исходной строки.
    assert str(restored.loc[0, "ИНН"]) == "123"
    assert restored.loc[0, "Итоговый скоринг"] == 75.5
