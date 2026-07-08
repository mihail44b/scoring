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
import numpy as np

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


@app.post("/api/score/full")
async def score_full(file: UploadFile = File(...)):
    """
    Полный расчет скоринга с возвращением JSON-данных для дашборда.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    # Чтение
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

    # Расчет
    try:
        df_feat = build_features(df)
        df_scored = apply_rules(df_feat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при расчете скоринга: {str(e)}"
        )

    # Подготовка данных для JSON (замена NaN, Inf -> None)
    df_clean = df_scored.copy()
    
    # Ищем ключевые колонки
    def find_col(prefixes):
        for pref in prefixes:
            col = next((c for c in df_clean.columns if pref.lower() in str(c).lower()), None)
            if col:
                return col
        return None

    address_col = find_col(["адрес", "регион", "местонахождение"])
    industry_col = find_col(["оквэд", "отрасль"])
    revenue_col = find_col(["выручка", "доход"])

    # Приводим к общему виду для UI
    df_clean["ui_inn"] = df_clean.get("ИНН", pd.Series("", index=df_clean.index)).astype(str).str.strip()
    df_clean["ui_name"] = df_clean.get("Краткое наименование", df_clean.get("Название", pd.Series("Неизвестно", index=df_clean.index)))
    df_clean["ui_address"] = df_clean[address_col] if address_col else "Не указан"
    df_clean["ui_industry"] = df_clean[industry_col] if industry_col else "Не указана"
    df_clean["ui_revenue"] = df_clean[revenue_col] if revenue_col else 0

    # Замена NaN -> None для корректного JSON
    df_clean = df_clean.replace({np.nan: None, pd.NA: None})
    
    records = df_clean.to_dict(orient="records")

    # Считаем агрегированные метрики для дашборда
    total = len(df_scored)
    
    segment_counts = df_scored["scoring_segment"].value_counts().to_dict()
    for seg in ["Горячий", "Тёплый", "Холодный"]:
        if seg not in segment_counts:
            segment_counts[seg] = 0

    chuvasia_mask = df_scored["A_region_coeff"] > 1.0
    chuvasia_count = int(chuvasia_mask.sum())
    
    redistributed_mask = df_scored["scoring_weights_mode"] == "перераспределение (без A)"
    redistributed_count = int(redistributed_mask.sum())

    # Средние баллы
    avg_score = round(float(df_scored["scoring_total"].mean()), 2) if total > 0 else 0
    avg_a = round(float(df_scored["A_score"].mean()), 2) if total > 0 else 0
    avg_b = round(float(df_scored["B_score"].mean()), 2) if total > 0 else 0
    avg_c = round(float(df_scored["C_score"].mean()), 2) if total > 0 else 0
    avg_d = round(float(df_scored["D_score"].mean()), 2) if total > 0 else 0
    avg_e = round(float(df_scored["E_score"].mean()), 2) if total > 0 else 0

    # Самые частые нарушения/причины
    # A_stop_factor == 0 — выручка ниже порога (для стандартного расчета)
    a_stopped = int((df_scored["A_stop_factor"] == 0).sum())
    c_stopped = int((df_scored["C_stop_factor"] == 0).sum())

    stats = {
        "total": total,
        "segments": segment_counts,
        "chuvasia_count": chuvasia_count,
        "redistributed_count": redistributed_count,
        "averages": {
            "total": avg_score,
            "A": avg_a,
            "B": avg_b,
            "C": avg_c,
            "D": avg_d,
            "E": avg_e,
        },
        "stops": {
            "revenue_stop": a_stopped,
            "industry_stop": c_stopped
        }
    }

    return {
        "validation": {
            "is_valid": validation.is_valid,
            "row_count": validation.row_count,
            "warnings": validation.warnings,
            "available_categories": validation.available_categories,
        },
        "stats": stats,
        "records": records,
    }


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
    
    df_clean = df[existing].replace({np.nan: None, pd.NA: None})
    preview = df_clean.head(10).to_dict(orient="records")

    return {
        "validation": {
            "is_valid": validation.is_valid,
            "row_count": validation.row_count,
            "warnings": validation.warnings,
            "available_categories": validation.available_categories,
        },
        "preview": preview,
    }

