"""
Категория E — Юридический статус и риски (участник 4).

Логика 1:1 повторяет формулы из Excel-листа «Категория E Юридический статус»
(столбцы H–M):
  H — балл по ликвидации (100, если нет отметки о ликвидации, иначе 0)
  I — балл по ОКФС (справочник, 4 тира: 100/60/30/0, дефолт 50)
  J — балл по ОКОПФ (справочник, 4 тира: 100/60/30/0, дефолт 50)
  K — балл по ИНН руководителя (100, если заполнен, иначе 50)
  L — итоговый балл
  M — стоп-фактор (0, если компания в процессе ликвидации)
"""
from __future__ import annotations

import os
import json
import pandas as pd
import numpy as np

_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

def _load_config():
    path = os.path.join(_CONF_DIR, "category_e_config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _load_weights():
    path = os.path.join(_CONF_DIR, "weights.json")
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
        return config["categories"]["E_legal_status"]["features"]


def _load_reference(filename: str) -> dict:
    path = os.path.join(_CONF_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def _load_okfs() -> dict:
    return _load_reference("okfs.json")


def _load_okopf() -> dict:
    return _load_reference("okopf.json")


def _get_series(df: pd.DataFrame, column_name: str) -> pd.Series | None:
    """Возвращает колонку по точному имени (с учётом лишних пробелов)."""
    normalized = {str(c).strip(): c for c in df.columns}
    real_col = normalized.get(column_name.strip())
    return df[real_col] if real_col is not None else None


def _score_from_reference(
    code_col: pd.Series | None,
    ref_map: dict,
    default_score: float,
    n_rows: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Возвращает (score, is_unknown):
      score      — балл по справочнику (default_score, если кода нет в справочнике
                   или поле пустое);
      is_unknown — True там, где код ЗАПОЛНЕН, но отсутствует в справочнике
                   (это и есть кандидаты на ручную проверку / актуализацию справочника,
                   в отличие от просто пустых полей).
    """
    if code_col is None:
        return np.full(n_rows, default_score), np.zeros(n_rows, dtype=bool)

    code_numeric = pd.to_numeric(code_col, errors="coerce")
    is_filled = code_numeric.notna()
    score = code_numeric.map(ref_map)
    is_unknown = (is_filled & score.isna()).to_numpy()
    score = score.fillna(default_score).to_numpy(dtype=float)
    return score, is_unknown


def score_category_e(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    n_rows = len(result)

    # Загрузка конфигов
    config = _load_config()
    weights = _load_weights()
    COLUMN_MAP = config["column_map"]
    DEFAULT_OKFS_SCORE = config["default_scores"]["okfs"]
    DEFAULT_OKOPF_SCORE = config["default_scores"]["okopf"]
    E_WEIGHTS = weights

    okfs_map = _load_okfs()
    okopf_map = _load_okopf()

    liq_col = _get_series(result, COLUMN_MAP["liquidation"])
    okfs_col = _get_series(result, COLUMN_MAP["okfs"])
    okopf_col = _get_series(result, COLUMN_MAP["okopf"])
    inn_col = _get_series(result, COLUMN_MAP["inn_manager"])

    # H: балл по ликвидации — 100, если поле пустое (компания действует),
    # 0, если есть отметка о ликвидации
    if liq_col is not None:
        s_liq = np.where(
            liq_col.isna() | (liq_col.astype(str).str.strip() == ""),
            100.0, 0.0,
        )
    else:
        s_liq = np.full(n_rows, 100.0)

    # I / J: баллы по справочникам ОКФС / ОКОПФ + флаги "код не найден в справочнике"
    s_okfs, okfs_unknown = _score_from_reference(okfs_col, okfs_map, DEFAULT_OKFS_SCORE, n_rows)
    s_okopf, okopf_unknown = _score_from_reference(okopf_col, okopf_map, DEFAULT_OKOPF_SCORE, n_rows)

    # K: балл по ИНН руководителя — 100, если заполнен, 50, если пуст
    if inn_col is not None:
        s_inn = np.where(
            inn_col.isna() | (inn_col.astype(str).str.strip() == ""),
            50.0, 100.0,
        )
    else:
        s_inn = np.full(n_rows, 50.0)

    # M: стоп-фактор — 0, если компания в процессе ликвидации
    stop_factor = np.where(s_liq == 100, 1, 0).astype(int)

    # L: итоговый балл
    weighted = (
        s_liq * E_WEIGHTS["liquidation"]
        + s_okfs * E_WEIGHTS["okfs"]
        + s_okopf * E_WEIGHTS["okopf"]
        + s_inn * E_WEIGHTS["inn_manager"]
    )
    total = np.where(s_liq == 0, 0.0, weighted) * stop_factor

    # completeness: доля заполненных полей из 4
    fields = [liq_col, okfs_col, okopf_col, inn_col]
    available_fields = [f for f in fields if f is not None]
    n_fields = len(available_fields)
    if n_fields > 0:
        count_present = sum(
            (f.notna() & (f.astype(str).str.strip() != "")).astype(int)
            for f in available_fields
        )
        completeness = np.round(count_present / n_fields * 100, 1)
    else:
        completeness = np.zeros(n_rows)

    # E_status: диагностика для ручной проверки —
    # коды ОКФС/ОКОПФ, которых нет ни в одном тире справочника
    # (по умолчанию им присваивается 50 баллов, но это стоит показать явно,
    # чтобы отличать "нейтральный код" от "код не размечен / справочник устарел")
    status = np.full(n_rows, "OK", dtype=object)
    both_unknown = okfs_unknown & okopf_unknown
    status[okfs_unknown & ~okopf_unknown] = "UNKNOWN_OKFS"
    status[okopf_unknown & ~okfs_unknown] = "UNKNOWN_OKOPF"
    status[both_unknown] = "UNKNOWN_OKFS_OKOPF"

    result["E_score"] = np.round(total, 1)
    result["E_completeness"] = completeness
    result["E_stop_factor"] = stop_factor
    result["E_status"] = status

    return result