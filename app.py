"""
app.py — точка входа FastAPI.

Эндпоинты:
  POST /score  — загрузить Excel-файл, получить скоринг в формате Excel
  GET  /health — проверка работоспособности
"""
import sys
import os
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import io

from core.validator import validate_input
from core.engine import calculate_scoring
from core.result_builder import build_result
from core.exporter import export_to_excel


app = FastAPI(
    title="Скоринг ДП (Динамический)",
    description="Универсальный сервис скоринга деловых партнёров на базе пресетов.",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "presets")

def get_active_preset() -> dict:
    """Загружает активный пресет. Пока хардкод на legacy_default.json."""
    path = os.path.join(PRESETS_DIR, "legacy_default.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/")
async def index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/settings")
async def settings_page():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "settings.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/score")
async def score_file(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .xlsx/.xls")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    preset = get_active_preset()
    validation = validate_input(df, preset)
    
    if not validation.is_valid:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Ошибка валидации входных данных",
                "errors": validation.errors,
                "warnings": validation.warnings,
            }
        )

    try:
        df_scored = calculate_scoring(df, preset)
        df_res = build_result(df_scored, preset, include_source=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

    xlsx_bytes = export_to_excel(df_res)

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=scoring_result.xlsx"},
    )


@app.post("/api/score/full")
async def score_full(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    preset = get_active_preset()
    validation = validate_input(df, preset)
    
    if not validation.is_valid:
        return JSONResponse(status_code=422, content={
            "detail": "Ошибка валидации",
            "errors": validation.errors,
            "warnings": validation.warnings,
        })

    try:
        df_scored = calculate_scoring(df, preset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка расчетов: {str(e)}")

    df_clean = df_scored.copy()
    
    def find_col(prefixes):
        for pref in prefixes:
            col = next((c for c in df_clean.columns if pref.lower() in str(c).lower()), None)
            if col: return col
        return None

    address_col = find_col(["адрес", "регион", "местонахождение"])
    industry_col = find_col(["оквэд", "отрасль"])
    revenue_col = find_col(["выручка", "доход"])

    df_clean["ui_inn"] = df_clean.get("ИНН", pd.Series("", index=df_clean.index)).astype(str).str.strip()
    df_clean["ui_name"] = df_clean.get("Краткое наименование", df_clean.get("Название", pd.Series("Неизвестно", index=df_clean.index)))
    df_clean["ui_address"] = df_clean[address_col] if address_col else "Не указан"
    df_clean["ui_industry"] = df_clean[industry_col] if industry_col else "Не указана"
    df_clean["ui_revenue"] = df_clean[revenue_col] if revenue_col else 0

    df_clean = df_clean.replace({np.nan: None, pd.NA: None})
    records = df_clean.to_dict(orient="records")

    total = len(df_scored)
    segment_counts = df_scored.get("scoring_segment", pd.Series([], dtype=str)).value_counts().to_dict()
    
    chuvasia_count = int((df_scored.get("_region_mult", pd.Series([1.0])) > 1.0).sum()) if "_region_mult" in df_scored.columns else 0

    averages = {"total": round(float(df_scored.get("scoring_total", pd.Series([0])).mean()), 2) if total > 0 else 0}
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        col = f"{cat_id}_score"
        averages[cat_id] = round(float(df_scored.get(col, pd.Series([0])).mean()), 2) if total > 0 and col in df_scored.columns else 0

    a_stopped = int((df_scored.get("A_stop_factor", pd.Series([1])) == 0).sum()) if "A_stop_factor" in df_scored.columns else 0
    c_stopped = int((df_scored.get("C_stop_factor", pd.Series([1])) == 0).sum()) if "C_stop_factor" in df_scored.columns else 0

    return {
        "validation": {
            "is_valid": validation.is_valid,
            "row_count": validation.row_count,
            "warnings": validation.warnings,
            "available_categories": validation.available_categories,
        },
        "stats": {
            "total": total,
            "segments": segment_counts,
            "chuvasia_count": chuvasia_count,
            "averages": averages,
            "stops": {"revenue_stop": a_stopped, "industry_stop": c_stopped}
        },
        "records": records,
    }


@app.get("/api/settings/configs")
async def get_all_configs():
    configs = {}
    if not os.path.exists(PRESETS_DIR):
        return configs
    for filename in os.listdir(PRESETS_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(PRESETS_DIR, filename), "r", encoding="utf-8") as f:
                try: configs[filename] = json.load(f)
                except: configs[filename] = {"error": "Invalid JSON"}
    return configs


@app.post("/api/settings/configs")
async def update_configs(payload: dict):
    updated_files = []
    for filename, content in payload.items():
        if not filename.endswith(".json") or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail=f"Недопустимое имя файла: {filename}")
        if isinstance(content, dict):
            path = os.path.join(PRESETS_DIR, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            updated_files.append(filename)
    return {"status": "ok", "message": "Пресеты обновлены", "updated": updated_files}


@app.post("/score/preview")
async def score_preview(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)

    preset = get_active_preset()
    validation = validate_input(df, preset)
    df_scored = calculate_scoring(df, preset)

    preview_cols = preset.get("id_columns", [])
    for cat in preset.get("categories", []):
        preview_cols.append(f"{cat['id']}_score")
    preview_cols.extend(["scoring_total", "enrichment_priority", "scoring_segment"])
    
    existing = [c for c in preview_cols if c in df_scored.columns]
    df_clean = df_scored[existing].replace({np.nan: None, pd.NA: None})
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
