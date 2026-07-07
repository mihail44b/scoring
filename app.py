"""
app.py — точка входа FastAPI (участник 5).

Эндпоинты:
  POST /score  — загрузить Excel-файл, получить скоринг в формате Excel
  GET  /health — проверка работоспособности

Оркестрация:
  1. Приём файла
  2. Валидация структуры
  3. Вызов категорийных функций через feature_builder
  4. Применение весов и сегментации через rules_engine
  5. Формирование объяснений
  6. Сборка результата и экспорт
"""
import sys
import os

# Добавляем dp_scoring в sys.path для корректных импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse
import pandas as pd
import io

from core.validator import validate_input
from core.feature_builder import build_features
from core.rules_engine import apply_rules
from core.result_builder import build_result
from core.exporter import export_to_excel


app = FastAPI(
    title="Скоринг ДП",
    description=(
        "Сервис скоринга деловых партнёров.\n\n"
        "Загрузите Excel-файл с данными компаний → "
        "получите файл с рассчитанными баллами по 5 категориям и итоговым скорингом."
    ),
    version="0.1.0",
)


@app.get("/")
async def index():
    """Главная страница с загрузкой файла."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    """Проверка работоспособности."""
    return {"status": "ok", "version": "0.1.0"}


@app.post(
    "/score",
    summary="Скоринг Excel-файла",
    description=(
        "Загрузите Excel-файл (формат .xlsx) с данными компаний.\n"
        "Возвращает Excel-файл с рассчитанными баллами."
    ),
)
async def score_file(file: UploadFile = File(..., description="Excel-файл (.xlsx)")):
    """
    Основной эндпоинт скоринга.

    Принимает Excel-файл, обрабатывает все 5 категорий,
    возвращает Excel с результатами.
    """
    # Проверка формата
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только файлы .xlsx"
        )

    # Чтение файла
    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка чтения файла: {str(e)}"
        )

    # Валидация
    validation = validate_input(df)
    if not validation.is_valid:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Ошибка валидации входных данных",
                "errors": validation.errors,
                "warnings": validation.warnings,
            }
        )

    # Обработка
    try:
        df = build_features(df)
        df = apply_rules(df)
        df = build_result(df, include_source=True)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки: {str(e)}"
        )

    # Экспорт
    xlsx_bytes = export_to_excel(df)

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=scoring_result.xlsx"
        },
    )


@app.post("/score/preview")
async def score_preview(file: UploadFile = File(...)):
    """
    Превью результатов скоринга в JSON (первые 10 строк).
    Полезно для отладки.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)

    validation = validate_input(df)

    df = build_features(df)
    df = apply_rules(df)

    preview_cols = [
        "ИНН", "Краткое наименование",
        "A_score", "B_score", "C_score", "D_score", "E_score",
        "scoring_total", "scoring_segment",
    ]
    existing = [c for c in preview_cols if c in df.columns]
    preview = df[existing].head(10)

    return {
        "validation": {
            "is_valid": validation.is_valid,
            "row_count": validation.row_count,
            "warnings": validation.warnings,
            "available_categories": validation.available_categories,
        },
        "preview": preview.to_dict(orient="records"),
    }
