"""
app.py — точка входа FastAPI.

Эндпоинты:
  POST /score  — загрузить Excel-файл, получить скоринг в формате Excel
  GET  /health — проверка работоспособности
"""
import sys
import os
import re
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


# ─── Справочники и хелперы для реестра компаний ────────────────────────────

PLACEHOLDER_VALUES = {"", "-", "—", "–", "nan", "none", "null", "н/д", "н\\д", "не указано", "не указан"}

FEDERAL_CITIES = [
    (re.compile(r"\bг\.?\s*москва\b", re.I), "г. Москва"),
    (re.compile(r"\bсанкт[\s-]?петербург\b", re.I), "г. Санкт-Петербург"),
    (re.compile(r"\bсевастополь\b", re.I), "г. Севастополь"),
]

REGION_KEYWORDS = re.compile(
    r"(республика|обл\.|область|\bкрай\b|автоном\w*\s*округ|авт\.\s*округ)", re.I
)
MUNICIPAL_EXCLUDE = re.compile(r"(городской округ|г\.о\.|муницип|м\.о\.)", re.I)


def _clean_field(value) -> str:
    """Возвращает строковое значение поля или '' если это плейсхолдер/пусто."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    if s.lower() in PLACEHOLDER_VALUES:
        return ""
    return s


def _split_multi(value: str, sep: str = ",") -> list:
    """Разбивает многозначное поле (email/сайты/телефоны) на список непустых значений."""
    if not value:
        return []
    parts = [p.strip() for p in value.split(sep)]
    return [p for p in parts if p and p.lower() not in PLACEHOLDER_VALUES]


def extract_region(address: str) -> str:
    """
    Извлекает название региона РФ из строки адреса. Поддерживает форматы
    с почтовым индексом в начале и без него, разный порядок компонентов.
    """
    addr = _clean_field(address)
    if not addr:
        return "Регион не определён"

    for pattern, canon_name in FEDERAL_CITIES:
        if pattern.search(addr):
            return canon_name

    parts = [p.strip(" .") for p in addr.split(",") if p.strip(" .")]
    for part in parts:
        if REGION_KEYWORDS.search(part) and not MUNICIPAL_EXCLUDE.search(part):
            cleaned = re.sub(r"\s+", " ", part).strip(" .")
            if cleaned.isupper():
                cleaned = cleaned.title()
            return cleaned

    return "Регион не определён"


def _contact_field(raw_value, sep: str = ",") -> dict:
    """Строит диагностический объект для контактного поля (телефон/email/сайт)."""
    clean = _clean_field(raw_value)
    values = _split_multi(clean, sep) if clean else []
    present = len(values) > 0
    return {
        "present": present,
        "count": len(values),
        "display": values[0] if values else "нет данных",
        "extra": len(values) - 1 if len(values) > 1 else 0,
    }


def _quality_label(pct: float) -> str:
    if pct >= 80:
        return "Высокое"
    if pct >= 45:
        return "Среднее"
    return "Низкое"


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
            if col:
                return col
        return None

    address_col = find_col(["адрес", "регион", "местонахождение"])
    industry_col = find_col(["оквэд наименование", "отрасль"])
    okved_code_col = find_col(["оквэд"])
    revenue_col = find_col(["выручка", "доход"])
    phone_col = find_col(["телефон"])
    email_col = find_col(["email", "e-mail", "почта"])
    website_col = find_col(["web-сайт", "web сайт", "сайт"])
    manager_col = find_col(["руководитель"])
    position_col = find_col(["должность"])
    tax_col = find_col(["налоговый режим"])

    # ── Базовые идентификаторы ──────────────────────────────────────────────
    df_clean["ui_inn"] = df_clean.get("ИНН", pd.Series("", index=df_clean.index)).astype(str).str.strip()
    df_clean["ui_name"] = df_clean.get(
        "Краткое наименование", df_clean.get("Название", pd.Series("Неизвестно", index=df_clean.index))
    )
    df_clean["ui_address"] = df_clean[address_col] if address_col else "Не указан"
    df_clean["ui_industry"] = df_clean[industry_col] if industry_col else "Не указана"
    df_clean["ui_okved_code"] = df_clean[okved_code_col] if okved_code_col else None
    df_clean["ui_revenue"] = df_clean[revenue_col] if revenue_col else None
    df_clean["ui_tax_regime"] = df_clean[tax_col] if tax_col else None

    # ── Регион (полноценное извлечение, не только Чувашия) ─────────────────
    df_clean["ui_region"] = df_clean["ui_address"].apply(extract_region)

    # ── Диагностика: выручка отсутствует в источнике (а не просто ниже порога) ──
    revenue_missing = pd.Series(True, index=df_clean.index)
    if revenue_col:
        revenue_missing = pd.to_numeric(df_clean[revenue_col], errors="coerce").isna()
    df_clean["ui_revenue_missing"] = revenue_missing

    # ── Стоп-факторы: сводный флаг + список сработавших категорий ──────────
    cat_ids = [c["id"] for c in preset.get("categories", [])]
    stop_cols = [f"{cid}_stop_factor" for cid in cat_ids if f"{cid}_stop_factor" in df_clean.columns]

    def _stopped_list(row):
        return [cid for cid, col in zip(cat_ids, stop_cols) if col in row and row[col] == 0]

    if stop_cols:
        df_clean["ui_stopped_categories"] = df_clean[stop_cols].apply(
            lambda row: [cid for cid, col in zip(cat_ids, stop_cols) if row[col] == 0], axis=1
        )
        df_clean["ui_any_stop"] = df_clean[stop_cols].apply(lambda row: bool((row == 0).any()), axis=1)
    else:
        df_clean["ui_stopped_categories"] = [[] for _ in range(len(df_clean))]
        df_clean["ui_any_stop"] = False

    # ── Контакты: статус наличия + количество значений в каждом поле ───────
    df_clean["ui_contact_phone"] = df_clean[phone_col].apply(_contact_field) if phone_col else [_contact_field(None)] * len(df_clean)
    df_clean["ui_contact_email"] = df_clean[email_col].apply(_contact_field) if email_col else [_contact_field(None)] * len(df_clean)
    df_clean["ui_contact_website"] = df_clean[website_col].apply(_contact_field) if website_col else [_contact_field(None)] * len(df_clean)
    df_clean["ui_manager"] = df_clean[manager_col].apply(_clean_field) if manager_col else ""
    df_clean["ui_position"] = df_clean[position_col].apply(_clean_field) if position_col else ""
    df_clean["ui_has_manager"] = df_clean["ui_manager"].apply(lambda v: bool(v))

    contact_present_count = (
        df_clean["ui_contact_phone"].apply(lambda c: c["present"]).astype(int)
        + df_clean["ui_contact_email"].apply(lambda c: c["present"]).astype(int)
        + df_clean["ui_contact_website"].apply(lambda c: c["present"]).astype(int)
        + df_clean["ui_has_manager"].astype(int)
    )
    df_clean["ui_contact_completeness"] = (contact_present_count / 4.0 * 100).round(0)

    # ── Оценка полезности/качества данных по компании ──────────────────────
    # Базируется на общей полноте данных по всем категориям скоринга (scoring_entropy),
    # плюс контактная доступность — то, что реально нужно продавцу для связи.
    overall_completeness = 100.0 - df_clean.get("scoring_entropy", pd.Series(0.0, index=df_clean.index)).fillna(0.0)
    quality_pct = (overall_completeness * 0.6 + df_clean["ui_contact_completeness"] * 0.4).clip(0, 100).round(0)
    df_clean["ui_data_quality_pct"] = quality_pct
    df_clean["ui_data_quality_label"] = quality_pct.apply(_quality_label)
    # "Нужно ли обогащение" — низкое качество данных, но лид не отсеян стоп-фактором
    df_clean["ui_needs_enrichment"] = (quality_pct < 80) & (~df_clean["ui_any_stop"])

    df_clean = df_clean.replace({np.nan: None, pd.NA: None})
    records = df_clean.to_dict(orient="records")

    # ── Статистика для дашборда ─────────────────────────────────────────────
    total = len(df_scored)
    segment_counts = df_scored.get("scoring_segment", pd.Series([], dtype=str)).value_counts().to_dict()

    averages = {"total": round(float(df_scored.get("scoring_total", pd.Series([0])).mean()), 2) if total > 0 else 0}
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        col = f"{cat_id}_score"
        averages[cat_id] = round(float(df_scored.get(col, pd.Series([0])).mean()), 2) if total > 0 and col in df_scored.columns else 0

    # Средний балл по каждому сегменту (для трёх блоков "горячие/тёплые/холодные")
    seg_labels = [s["label"] for s in preset.get("segments", {}).values()]
    segment_avg = {}
    if "scoring_total" in df_scored.columns and "scoring_segment" in df_scored.columns:
        for lbl in seg_labels:
            subset = df_scored.loc[df_scored["scoring_segment"] == lbl, "scoring_total"]
            segment_avg[lbl] = round(float(subset.mean()), 2) if len(subset) else 0

    # Разбивка стоп-факторов по каждой категории (не только A/C — универсально)
    stops_breakdown = {}
    for cid in cat_ids:
        col = f"{cid}_stop_factor"
        if col in df_scored.columns:
            stops_breakdown[cid] = int((df_scored[col] == 0).sum())
    any_stop_total = int(df_clean["ui_any_stop"].sum())

    # Регионы: полное распределение количества компаний по регионам
    region_counts = df_clean["ui_region"].value_counts().to_dict()
    region_counts = {str(k): int(v) for k, v in region_counts.items()}

    # Средний скоринг по региону (топ регионов), полезно для графика
    region_avg_score = {}
    if "scoring_total" in df_scored.columns:
        tmp = df_scored.copy()
        tmp["ui_region"] = df_clean["ui_region"]
        grp = tmp.groupby("ui_region")["scoring_total"].mean().round(1)
        region_avg_score = {str(k): float(v) for k, v in grp.to_dict().items()}

    # Распределение по качеству данных
    quality_dist = df_clean["ui_data_quality_label"].value_counts().to_dict()

    return {
        "validation": {
            "is_valid": validation.is_valid,
            "row_count": validation.row_count,
            "warnings": validation.warnings,
            "available_categories": validation.available_categories,
        },
        "stats": {
            "total": total,
            "segments_config": preset.get("segments", {}),
            "segments": segment_counts,
            "segment_avg_score": segment_avg,
            "averages": averages,
            "stops": {
                "by_category": stops_breakdown,
                "total_companies_stopped": any_stop_total,
                # обратная совместимость со старыми полями
                "revenue_stop": stops_breakdown.get("A", 0),
                "industry_stop": stops_breakdown.get("C", 0),
            },
            "regions": region_counts,
            "region_avg_score": region_avg_score,
            "quality_distribution": quality_dist,
            "categories_meta": [{"id": c["id"], "name": c.get("name", c["id"])} for c in preset.get("categories", [])],
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