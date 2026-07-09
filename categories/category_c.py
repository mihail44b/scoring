"""
Категория C — Отраслевая релевантность

Определяет ценность лида на основе его сферы деятельности и налогового режима.

Возвращаемые колонки (добавляются к исходному DataFrame):
  1. C_score        — Итоговый балл категории (от 0 до 100). 
                      Вычисляется как взвешенная сумма баллов за ОКВЭД и Налог.
  2. C_completeness — Полнота данных (0%, 50% или 100%).
                      Показывает, какая доля признаков (из 2-х) физически заполнена.
  3. C_stop_factor  — Метка критического отсева (1 = всё ок, 0 = стоп-фактор).
                      0 ставится, если класс ОКВЭД относится к Тир 4 (бюджет/НКО).
  4. C_status       — Текстовая диагностика расхождений со справочниками:
                      "ок"                           — данные найдены в справочнике (или пустые)
                      "ОКВЭД: не в справочнике (XX)" — класс XX не найден в okved_tiers.json
                      "Нал. режим: не в справочнике" — режим не найден в tax_regimes.json

Примечание: Веса признаков внутри категории (например, ОКВЭД=0.8, Налог=0.2) 
настраиваются в файле config/weights.json и загружаются динамически.
"""
import os
import pandas as pd
import numpy as np
import json

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


# Загрузка справочников

def _load_okved_tiers() -> dict:
    """Загружаем конфиг для ОКВЭД, в котором прописаны баллы."""
    path = os.path.join(_CONF_DIR, "okved_tiers.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_tax_regimes() -> dict:
    """Загружаем конфиг для налогового режима, в котором прописаны баллы."""
    path = os.path.join(_CONF_DIR, "tax_regimes.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_feature_weights() -> tuple[float, float]:
    """Загружает веса признаков для категории C из общего конфига."""
    path = os.path.join(_CONF_DIR, "weights.json")
    if not os.path.exists(path):
        return 0.8, 0.2
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    try:
        w = config["categories"]["C_industry_relevance"]["features"]
        okved_w = float(w.get("okved", 0.8))
        tax_w = float(w.get("tax_regime", 0.2))
        
        # Нормализация: если в конфиге вручную вбили 0.9 и 0.5, приводим к долям от 1.0
        total_w = okved_w + tax_w
        if total_w <= 0:
            return 0.8, 0.2
        return okved_w / total_w, tax_w / total_w
    except KeyError:
        return 0.8, 0.2


# Вспомогательные функции

def _extract_class(okved_code) -> str:
    """Вытаскиваем значение класса ОКВЭД (первое число до точки)."""
    if pd.isna(okved_code) or str(okved_code).strip() == "":
        return ""
    code = str(okved_code).strip()
    dot_pos = code.find(".")
    cls = code[:dot_pos] if dot_pos > 0 else code
    return cls.zfill(2)  # Восстанавливаем нули, которые мог съесть Excel ("1" -> "01")


def _get_series(df, col_prefix):
    """Поиск колонки по вхождению подстроки (без учёта регистра)."""
    matched = next((c for c in df.columns if col_prefix.lower() in str(c).lower()), None)
    return df[matched] if matched else None


# Основная функция скоринга

def score_category_c(df: pd.DataFrame) -> pd.DataFrame:
    """
    Вход: df со всеми колонками.
    Выход: df + C_score, C_completeness, C_stop_factor, C_status.
    """
    result = df.copy()
    okved_tiers = _load_okved_tiers()
    tax_regimes = _load_tax_regimes()

    okved_col = _get_series(result, "ОКВЭД")
    tax_col = _get_series(result, "Налоговый режим")

    # ─── Обработка ОКВЭД ─────────────────────────────────────────────
    if okved_col is not None:
        classes = okved_col.apply(_extract_class)
        # Балл: ищем в справочнике, иначе 0
        scores_okved = classes.map(okved_tiers).fillna(0.0).astype(float)
        # Диагностика: фиксируем только неизвестные значения
        is_unknown = (classes != "") & (~classes.isin(okved_tiers.keys()))
        status_okved = np.where(is_unknown, "ОКВЭД: не в справочнике (" + classes + ")", "")
    else:
        classes = pd.Series("", index=result.index)
        scores_okved = pd.Series(0.0, index=result.index)
        status_okved = pd.Series("", index=result.index)

    # ─── Обработка Налогового режима ─────────────────────────────────
    if tax_col is not None:
        # Приводим к верхнему регистру, убираем пробелы, обрабатываем синонимы и пустые значения
        tax_clean = tax_col.fillna("").astype(str).str.strip().str.upper()
        tax_clean = tax_clean.replace({"ОСНО": "ОСН", "NAN": "", "NONE": ""})
        
        # Балл: ищем в справочнике, иначе 0
        scores_tax = tax_clean.map(tax_regimes).fillna(0.0).astype(float)
        # Диагностика: фиксируем только неизвестные значения
        is_unknown = (tax_clean != "") & (~tax_clean.isin(tax_regimes.keys()))
        status_tax = np.where(is_unknown, "Нал. режим: не в справочнике (" + tax_clean + ")", "")
    else:
        tax_clean = pd.Series("", index=result.index)
        scores_tax = pd.Series(0.0, index=result.index)
        status_tax = pd.Series("", index=result.index)

    # ─── Формирование C_status ───────────────────────────────────────
    # Склеиваем статусы. Если оба пустые, заменяем на "ок"
    combined = pd.Series(status_okved) + " | " + pd.Series(status_tax)
    statuses = combined.str.strip(" |").replace("", "ок")

    # ─── Стоп-фактор ────────────────────────────────────────────────
    # Тир 4 (бюджет/НКО) — жёсткий отсев
    tier4_classes = {code for code, score in okved_tiers.items() if score == 0}
    stop_factor = np.where(classes.isin(tier4_classes), 0, 1)

    # Итоговый балл
    weight_okved, weight_tax = _load_feature_weights()
    total = (weight_okved * scores_okved + weight_tax * scores_tax) * stop_factor

    # Полнота данных
    has_okved = (okved_col.notna() & (okved_col.astype(str).str.strip() != "")).astype(int) if okved_col is not None else 0
    has_tax = (tax_col.notna() & (tax_col.astype(str).str.strip() != "")).astype(int) if tax_col is not None else 0
    completeness = np.round((has_okved + has_tax) / 2 * 100, 1)

    # Запись результатов
    result["C_score"] = np.round(total, 1)
    result["C_completeness"] = completeness
    result["C_stop_factor"] = stop_factor
    result["C_status"] = statuses

    return result


# Утилиты для управления справочниками и конфигами

def set_category_c_feature_weights(okved_weight: float, tax_weight: float) -> None:
    """
    Изменяет веса признаков для категории C в общем конфиге weights.json.
    
    Args:
        okved_weight: Вес для ОКВЭД (например, 0.8)
        tax_weight: Вес для Налогового режима (например, 0.2)
    """
    if abs(okved_weight + tax_weight - 1.0) > 0.001:
        raise ValueError(f"Сумма весов должна быть равна 1.0 (получено {okved_weight} + {tax_weight})")
        
    path = os.path.join(_CONF_DIR, "weights.json")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    if "features" not in config["categories"]["C_industry_relevance"]:
        config["categories"]["C_industry_relevance"]["features"] = {}
        
    config["categories"]["C_industry_relevance"]["features"]["okved"] = okved_weight
    config["categories"]["C_industry_relevance"]["features"]["tax_regime"] = tax_weight
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def add_okved_to_reference(class_code: str, score: int, tier: int = None) -> None:
    """
    Добавляет новый класс ОКВЭД в справочник.

    Args:
        class_code: класс ОКВЭД (например "99")
        score: балл (0, 30, 60 или 100)
        tier: номер тира (1-4), опционально для документирования
    """
    path = os.path.join(_CONF_DIR, "okved_tiers.json")
    data = _load_okved_tiers()

    if class_code in data:
        raise ValueError(f"Класс ОКВЭД '{class_code}' уже есть в справочнике (балл: {data[class_code]})")

    if score not in (0, 30, 60, 100):
        raise ValueError(f"Балл должен быть 0, 30, 60 или 100 (получено: {score})")

    data[class_code] = score
    # Сортируем по коду для читаемости
    data = dict(sorted(data.items(), key=lambda x: x[0]))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_tax_regime_to_reference(regime: str, score: int) -> None:
    """
    Добавляет новый налоговый режим в справочник.

    Args:
        regime: название режима (например "ПСН")
        score: балл (0-100)
    """
    path = os.path.join(_CONF_DIR, "tax_regimes.json")
    data = _load_tax_regimes()

    if regime in data:
        raise ValueError(f"Режим '{regime}' уже есть в справочнике (балл: {data[regime]})")

    data[regime] = score

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_unknown_values(df: pd.DataFrame) -> dict:
    """
    Сканирует DataFrame и возвращает значения, которые есть в данных,
    но отсутствуют в справочниках. Полезно для аналитиков, чтобы понять,
    какими записями нужно дополнить справочники.

    Returns:
        {
          "unknown_okved": [("45.12", "45"), ("99.00", "99"), ...],  # (полный код, класс)
          "unknown_tax": ["ПСН", "АУСН", ...]
        }
    """
    okved_tiers = _load_okved_tiers()
    tax_regimes = _load_tax_regimes()

    okved_col = _get_series(df, "ОКВЭД")
    tax_col = _get_series(df, "Налоговый режим")

    unknown_okved = set()
    unknown_tax = set()

    if okved_col is not None:
        for val in okved_col.dropna().unique():
            code = str(val).strip()
            if code == "":
                continue
            cls = _extract_class(code)
            if cls and cls not in okved_tiers:
                unknown_okved.add((code, cls))

    if tax_col is not None:
        for val in tax_col.dropna().unique():
            regime = str(val).strip()
            if regime and regime not in tax_regimes:
                unknown_tax.add(regime)

    return {
        "unknown_okved": sorted(unknown_okved),
        "unknown_tax": sorted(unknown_tax),
    }
