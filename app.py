"""
app.py — Главный контроллер FastAPI.
Управляет маршрутизацией, принимает файлы, вызывает логику скоринга (движок) 
и отдает результаты как в виде файлов, так и в формате JSON для дашборда.
"""
import sys
import os
import re
import json
import io
from typing import List, Dict, Any, Optional, Union

import pandas as pd
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Cookie, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.validator import validate_input
from core.engine import calculate_scoring
from core.result_builder import build_result
from core.exporter import export_to_excel
from core.session_store import init_db, save_session, get_sessions, get_session_data, delete_session, cleanup_old_sessions
import uuid
import urllib.parse

TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


# ─── 1. СПРАВОЧНИКИ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ────────────────────────────────
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
    """Очищает поле от мусора и плейсхолдеров. Возвращает пустую строку, если данных нет."""
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
    """Разбивает строку с несколькими контактами на список чистых значений."""
    if not value:
        return []
    parts = [p.strip() for p in value.split(sep)]
    return [p for p in parts if p and p.lower() not in PLACEHOLDER_VALUES]


def extract_region(address: str) -> str:
    """Извлекает нормализованное название региона РФ из неструктурированной строки адреса."""
    addr = _clean_field(address)
    if not addr:
        return "Регион не определён"

    # Проверка на города федерального значения
    for pattern, canon_name in FEDERAL_CITIES:
        if pattern.search(addr):
            return canon_name

    # Разбор составного адреса
    parts = [p.strip(" .") for p in addr.split(",") if p.strip(" .")]
    for part in parts:
        if REGION_KEYWORDS.search(part) and not MUNICIPAL_EXCLUDE.search(part):
            cleaned = re.sub(r"\s+", " ", part).strip(" .")
            if cleaned.isupper():
                cleaned = cleaned.title()
            return cleaned

    return "Регион не определён"


def _contact_field(raw_value, sep: str = ",") -> dict:
    """Формирует объект диагностики для контактного поля (наличие, количество, первое значение)."""
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
    """Определяет текстовый маркер качества данных на основе процента заполненности."""
    if pct >= 80:
        return "Высокое"
    if pct >= 45:
        return "Среднее"
    return "Низкое"


# ─── 2. ИНИЦИАЛИЗАЦИЯ FASTAPI ────────────────────────────────────────────────
app = FastAPI(
    title="Скоринг ДП (Динамический)",
    description="Универсальный сервис скоринга деловых партнёров на базе пресетов.",
    version="2.0.0",
)

# Подключение статических файлов (CSS, JS)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "presets")

# ─── Инициализация SQLite при старте сервера ──────────────────────────────────
init_db()
deleted = cleanup_old_sessions()
if deleted:
    print(f"[session_store] Очищено {deleted} устаревших сессий")


def _get_or_create_browser_id(request: Request) -> tuple[str, bool]:
    """Читает browser_id из cookie. Если нет — генерирует новый. Возвращает (id, is_new)."""
    browser_id = request.cookies.get("browser_id")
    if browser_id:
        return browser_id, False
    return str(uuid.uuid4()), True


def get_active_preset(preset_name: str = "legacy_default.json") -> dict:
    """Загружает пресет конфигурации по имени файла."""
    path = os.path.join(PRESETS_DIR, preset_name)
    if not os.path.exists(path):
        path = os.path.join(PRESETS_DIR, "legacy_default.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── 3. СХЕМЫ ВАЛИДАЦИИ КОНФИГУРАЦИЙ (PYDANTIC) ──────────────────────────────
class SegmentSchema(BaseModel):
    min_score: Union[int, float]
    label: str

class EnrichmentWeightsSchema(BaseModel):
    score_weight: float
    entropy_weight: float

class RegionalCoefficientsSchema(BaseModel):
    keywords: List[str]
    rules: Dict[str, Union[float, int]]

class ScoringMethodSchema(BaseModel):
    type: str
    params: Optional[Dict[str, Any]] = None

class FeatureSchema(BaseModel):
    id: str
    weight: float
    scoring_method: ScoringMethodSchema
    name: Optional[str] = None

class StopFactorSchema(BaseModel):
    type: str
    feature: Optional[str] = None
    operator: Optional[str] = None
    values_with_score: Optional[Union[int, float]] = None
    value: Optional[Any] = None
    features: Optional[List[str]] = None

class DiagnosticColumnSchema(BaseModel):
    id: str
    name: str
    type: str
    features: List[str]
    values: Optional[Dict[str, str]] = None

class CategoryModifierSchema(BaseModel):
    type: str
    features: List[str]

class CategorySchema(BaseModel):
    id: str
    name: str
    weight: float
    stop_factors: List[StopFactorSchema] = []
    features: List[FeatureSchema] = []
    diagnostic_columns: Optional[List[DiagnosticColumnSchema]] = []
    category_modifiers: Optional[List[CategoryModifierSchema]] = []

class PresetSchema(BaseModel):
    id_columns: Optional[List[str]] = None
    segments: Dict[str, SegmentSchema]
    enrichment_weights: EnrichmentWeightsSchema
    regional_coefficients: Optional[RegionalCoefficientsSchema] = None
    categories: List[CategorySchema]


# ─── 4. ВЕБ-ИНТЕРФЕЙС (HTML РОУТЫ) ───────────────────────────────────────────
@app.get("/")
async def index():
    """Отдает главную страницу дашборда."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/settings")
async def settings_page():
    """Отдает страницу панели настроек пресетов."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "settings.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    """Проверка жизнеспособности сервиса."""
    return {"status": "ok", "version": "2.0.0"}


# ─── 5. API СКОРИНГА И ОБРАБОТКИ ФАЙЛОВ ──────────────────────────────────────
@app.post("/score")
async def score_file(file: UploadFile = File(...)):
    """
    Принимает Excel-файл, проводит полный скоринг и возвращает готовый Excel-файл.
    Используется для кнопки "Скачать Excel" в интерфейсе.
    """
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
        headers={"Content-Disposition": f"attachment; filename=scoring_result.xlsx"},
    )


@app.post("/api/score/full")
async def score_full(request: Request, file: UploadFile = File(...), preset_name: str = "legacy_default.json"):
    """
    Принимает Excel-файл, проводит скоринг и возвращает агрегированные данные (JSON).
    Используется дашбордом для построения графиков и отрисовки реестра.
    Автоматически сохраняет результат в SQLite и привязывает к browser_id из cookie.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        
        # Сохраняем файл временно, чтобы скачивание работало после перезагрузки дашборда
        file_id = str(uuid.uuid4())
        temp_path = os.path.join(TEMP_DIR, f"{file_id}.xlsx")
        with open(temp_path, "wb") as f:
            f.write(content)
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    preset = get_active_preset(preset_name)
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

    # Поиск стандартных колонок для нужд UI дашборда
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

    # Базовые идентификаторы UI
    df_clean["ui_inn"] = df_clean.get("ИНН", pd.Series("", index=df_clean.index)).astype(str).str.strip()
    df_clean["ui_name"] = df_clean.get("Краткое наименование", df_clean.get("Название", pd.Series("Неизвестно", index=df_clean.index)))
    df_clean["ui_address"] = df_clean[address_col] if address_col else "Не указан"
    df_clean["ui_industry"] = df_clean[industry_col] if industry_col else "Не указана"
    df_clean["ui_okved_code"] = df_clean[okved_code_col] if okved_code_col else None
    df_clean["ui_revenue"] = df_clean[revenue_col] if revenue_col else None
    df_clean["ui_tax_regime"] = df_clean[tax_col] if tax_col else None

    # Полноценное извлечение региона
    df_clean["ui_region"] = df_clean["ui_address"].apply(extract_region)

    # Диагностика: выручка отсутствует в самом источнике
    revenue_missing = pd.Series(True, index=df_clean.index)
    if revenue_col:
        revenue_missing = pd.to_numeric(df_clean[revenue_col], errors="coerce").isna()
    df_clean["ui_revenue_missing"] = revenue_missing

    # Сводка по стоп-факторам
    cat_ids = [c["id"] for c in preset.get("categories", [])]
    stop_cols = [f"{cid}_stop_factor" for cid in cat_ids if f"{cid}_stop_factor" in df_clean.columns]

    if stop_cols:
        df_clean["ui_stopped_categories"] = df_clean[stop_cols].apply(
            lambda row: [cid for cid, col in zip(cat_ids, stop_cols) if row[col] == 0], axis=1
        )
        df_clean["ui_any_stop"] = df_clean[stop_cols].apply(lambda row: bool((row == 0).any()), axis=1)
    else:
        df_clean["ui_stopped_categories"] = [[] for _ in range(len(df_clean))]
        df_clean["ui_any_stop"] = False

    # Контакты: статус и наличие
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

    # Оценка качества данных компании
    overall_completeness = 100.0 - df_clean.get("scoring_entropy", pd.Series(0.0, index=df_clean.index)).fillna(0.0)
    quality_pct = (overall_completeness * 0.6 + df_clean["ui_contact_completeness"] * 0.4).clip(0, 100).round(0)
    df_clean["ui_data_quality_pct"] = quality_pct
    df_clean["ui_data_quality_label"] = quality_pct.apply(_quality_label)
    
    # Флаг "Нужно обогащение" (Качество ниже 80% и нет стоп-факторов)
    df_clean["ui_needs_enrichment"] = (quality_pct < 80) & (~df_clean["ui_any_stop"])

    # Очистка NaN для отправки JSON
    df_clean = df_clean.replace({np.nan: None, pd.NA: None})
    records = df_clean.to_dict(orient="records")

    # ─── Сбор статистики для дашборда ───
    total = len(df_scored)
    segment_counts = df_scored.get("scoring_segment", pd.Series([], dtype=str)).value_counts().to_dict()

    averages = {"total": round(float(df_scored.get("scoring_total", pd.Series([0])).mean()), 2) if total > 0 else 0}
    for cat in preset.get("categories", []):
        cat_id = cat["id"]
        col = f"{cat_id}_score"
        averages[cat_id] = round(float(df_scored.get(col, pd.Series([0])).mean()), 2) if total > 0 and col in df_scored.columns else 0

    seg_labels = [s["label"] for s in preset.get("segments", {}).values()]
    segment_avg = {}
    if "scoring_total" in df_scored.columns and "scoring_segment" in df_scored.columns:
        for lbl in seg_labels:
            subset = df_scored.loc[df_scored["scoring_segment"] == lbl, "scoring_total"]
            segment_avg[lbl] = round(float(subset.mean()), 2) if len(subset) else 0

    stops_breakdown = {}
    for cid in cat_ids:
        col = f"{cid}_stop_factor"
        if col in df_scored.columns:
            stops_breakdown[cid] = int((df_scored[col] == 0).sum())
    any_stop_total = int(df_clean["ui_any_stop"].sum())

    region_counts = df_clean["ui_region"].value_counts().to_dict()
    region_counts = {str(k): int(v) for k, v in region_counts.items()}

    region_avg_score = {}
    if "scoring_total" in df_scored.columns:
        tmp = df_scored.copy()
        tmp["ui_region"] = df_clean["ui_region"]
        grp = tmp.groupby("ui_region")["scoring_total"].mean().round(1)
        region_avg_score = {str(k): float(v) for k, v in grp.to_dict().items()}

    quality_dist = df_clean["ui_data_quality_label"].value_counts().to_dict()

    response_data = {
        "file_id": file_id,
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

    # ─── Сохранение сессии в SQLite и установка cookie ───
    browser_id, is_new = _get_or_create_browser_id(request)
    
    session_id = save_session(
        browser_id=browser_id,
        file_id=file_id,
        file_name=file.filename,
        preset_name=preset_name,
        scoring_data=response_data,
    )
    response_data["session_id"] = session_id

    response = JSONResponse(content=response_data)
    if is_new:
        response.set_cookie(
            key="browser_id",
            value=browser_id,
            max_age=365 * 24 * 3600,  # 1 год
            httponly=False,            # JS должен читать для отладки
            samesite="lax",
        )
    return response

@app.get("/api/score/download/{file_id}")
async def download_scored_file(file_id: str, filename: str = "result.xlsx", preset_name: str = "legacy_default.json"):
    """
    Эндпоинт для скачивания файла после того, как он был загружен в /api/score/full.
    Восстанавливает исходный файл, применяет скоринг и отдает XLSX.
    """
    temp_path = os.path.join(TEMP_DIR, f"{file_id}.xlsx")
    if not os.path.exists(temp_path):
        raise HTTPException(status_code=404, detail="Файл не найден. Пожалуйста, загрузите базу заново.")
        
    try:
        df = pd.read_excel(temp_path, sheet_name=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    preset = get_active_preset(preset_name)
    validation = validate_input(df, preset)
    
    if not validation.is_valid:
        raise HTTPException(status_code=422, detail="Ошибка валидации файла при скачивании")

    try:
        df_scored = calculate_scoring(df, preset)
        df_res = build_result(df_scored, preset, include_source=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

    xlsx_bytes = export_to_excel(df_res)
    encoded_name = urllib.parse.quote(f"scored_{filename}")

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@app.post("/score/preview")
async def score_preview(file: UploadFile = File(...)):
    """Облегченный эндпоинт для превью (например, в песочнице настроек)."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Только .xlsx")

    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name=0)

    preset = get_active_preset()
    validation = validate_input(df, preset)

    if not validation.is_valid:
        return JSONResponse(status_code=422, content={
            "detail": "Ошибка валидации",
            "errors": validation.errors,
            "warnings": validation.warnings,
        })

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


# ─── 6. API НАСТРОЕК (ПРЕСЕТОВ) ──────────────────────────────────────────────
@app.get("/api/settings/configs")
async def get_all_configs():
    """Возвращает все доступные пресеты в виде JSON-словаря."""
    configs = {}
    if not os.path.exists(PRESETS_DIR):
        return configs
    for filename in os.listdir(PRESETS_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(PRESETS_DIR, filename), "r", encoding="utf-8") as f:
                try: 
                    configs[filename] = json.load(f)
                except: 
                    configs[filename] = {"error": "Invalid JSON"}
    return configs


@app.post("/api/settings/configs")
async def update_configs(payload: dict):
    """
    Принимает измененные пресеты от фронтенда панели настроек,
    строго валидирует их структуру с помощью Pydantic и сохраняет в файлы.
    """
    updated_files = []
    for filename, content in payload.items():
        if not filename.endswith(".json") or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail=f"Недопустимое имя файла: {filename}")
        
        if isinstance(content, dict):
            # Жесткая валидация структуры
            try:
                PresetSchema(**content)
            except ValidationError as e:
                error_msgs = []
                for err in e.errors():
                    loc = " -> ".join([str(l) for l in err["loc"]])
                    error_msgs.append(f"Поле '{loc}': {err['msg']}")
                raise HTTPException(status_code=422, detail=f"Ошибка структуры в {filename}: " + "; ".join(error_msgs))

            # Сохранение на диск
            path = os.path.join(PRESETS_DIR, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            updated_files.append(filename)
            
    return {"status": "ok", "message": "Пресеты успешно обновлены", "updated": updated_files}


class NewPresetRequest(BaseModel):
    filename: str

@app.post("/api/settings/configs/new")
async def create_preset(req: NewPresetRequest):
    """Создает новый пустой пресет."""
    filename = req.filename.strip()
    if not filename.endswith(".json"):
        filename += ".json"
    if "/" in filename or "\\" in filename or not filename:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
        
    path = os.path.join(PRESETS_DIR, filename)
    if os.path.exists(path):
        raise HTTPException(status_code=400, detail="Пресет с таким именем уже существует")
        
    empty_preset = {
        "segments": {},
        "enrichment_weights": { "score_weight": 0.6, "entropy_weight": 0.4 },
        "categories": []
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(empty_preset, f, ensure_ascii=False, indent=2)
        
    return {"status": "ok", "filename": filename, "content": empty_preset}

@app.delete("/api/settings/configs/{filename}")
async def delete_preset(filename: str):
    """Удаляет пресет."""
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
        
    if filename == "legacy_default.json":
        raise HTTPException(status_code=400, detail="Нельзя удалить системный пресет")
        
    path = os.path.join(PRESETS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Пресет не найден")
        
    os.remove(path)
    return {"status": "ok", "message": "Пресет удален"}


# ─── 7. API СЕССИЙ (COOKIES + SQLITE) ────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions(request: Request):
    """
    Возвращает список сохранённых сессий скоринга для текущего браузера.
    Идентификация — через cookie browser_id.
    Возвращает только метаданные (без тяжёлого scoring_data).
    """
    browser_id, is_new = _get_or_create_browser_id(request)
    
    if is_new:
        # Новый браузер — сессий нет, но ставим cookie
        response = JSONResponse(content={"sessions": []})
        response.set_cookie(
            key="browser_id",
            value=browser_id,
            max_age=365 * 24 * 3600,
            httponly=False,
            samesite="lax",
        )
        return response
    
    sessions = get_sessions(browser_id)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """
    Возвращает полные данные сессии (включая scoring_data) для восстановления дашборда.
    Проверяет принадлежность к текущему browser_id.
    """
    browser_id = request.cookies.get("browser_id")
    if not browser_id:
        raise HTTPException(status_code=401, detail="Cookie browser_id не найден")
    
    data = get_session_data(session_id, browser_id)
    if not data:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return data["scoring_data"]


@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str, request: Request):
    """Удаляет сессию скоринга."""
    browser_id = request.cookies.get("browser_id")
    if not browser_id:
        raise HTTPException(status_code=401, detail="Cookie browser_id не найден")
    
    deleted = delete_session(session_id, browser_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return {"status": "ok", "message": "Сессия удалена"}