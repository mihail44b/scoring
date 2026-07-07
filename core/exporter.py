"""
Exporter — выгрузка результатов в Excel.
"""
import io
import pandas as pd


def export_to_excel(df: pd.DataFrame) -> bytes:
    """
    Экспортирует DataFrame в Excel-файл (bytes).

    Returns:
        bytes содержимого .xlsx файла
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Скоринг", index=False)
    buf.seek(0)
    return buf.getvalue()
