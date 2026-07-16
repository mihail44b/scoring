"""
session_store.py — Модуль серверного хранения сессий скоринга.

Использует SQLite для персистентного хранения результатов расчётов.
Идентификация пользователя — через browser_id (UUID из cookie).
"""
import sqlite3
import uuid
import json
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Путь к файлу БД
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "sessions.db")

# Ограничения
MAX_SESSIONS_PER_BROWSER = 5
SESSION_TTL_DAYS = 30


def _get_connection() -> sqlite3.Connection:
    """Создаёт подключение к SQLite с row_factory для удобного доступа по именам колонок."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Лучшая производительность при конкурентном доступе
    return conn


def init_db():
    """Инициализирует базу данных: создаёт директорию и таблицу sessions."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    conn = _get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                browser_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                preset_name TEXT NOT NULL DEFAULT 'legacy_default.json',
                scoring_data TEXT NOT NULL,
                record_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_browser_id 
            ON sessions(browser_id)
        """)
        conn.commit()
    finally:
        conn.close()


def save_session(
    browser_id: str,
    file_id: str,
    file_name: str,
    preset_name: str,
    scoring_data: dict,
) -> str:
    """
    Сохраняет результат скоринга в SQLite.
    Если у этого browser_id уже есть сессия с таким же file_name + preset_name —
    обновляет её (заменяет результат свежим расчётом) вместо создания дубля.
    Если у браузера уже MAX_SESSIONS_PER_BROWSER сессий — удаляет самую старую.
    Возвращает ID сессии (существующей или новой).
    """
    now = datetime.utcnow().isoformat()
    record_count = len(scoring_data.get("records", []))
    scoring_json = json.dumps(scoring_data, ensure_ascii=False)
    
    conn = _get_connection()
    try:
        # Проверяем, есть ли уже сессия с таким же файлом и пресетом у этого браузера
        cursor = conn.execute(
            """SELECT id FROM sessions 
               WHERE browser_id = ? AND file_name = ? AND preset_name = ?""",
            (browser_id, file_name, preset_name)
        )
        existing_same = cursor.fetchone()
        
        if existing_same:
            # Обновляем существующую сессию свежими данными
            session_id = existing_same["id"]
            conn.execute(
                """UPDATE sessions 
                   SET file_id = ?, scoring_data = ?, record_count = ?, created_at = ?
                   WHERE id = ?""",
                (file_id, scoring_json, record_count, now, session_id)
            )
            conn.commit()
            return session_id
        
        # Новая комбинация файл+пресет — создаём новую сессию
        session_id = str(uuid.uuid4())
        
        # Проверяем количество существующих сессий
        cursor = conn.execute(
            "SELECT id FROM sessions WHERE browser_id = ? ORDER BY created_at ASC",
            (browser_id,)
        )
        existing = cursor.fetchall()
        
        # Удаляем лишние (оставляем место для новой)
        if len(existing) >= MAX_SESSIONS_PER_BROWSER:
            to_delete = existing[:len(existing) - MAX_SESSIONS_PER_BROWSER + 1]
            for row in to_delete:
                conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
        
        # Сохраняем новую сессию
        conn.execute(
            """INSERT INTO sessions (id, browser_id, file_id, file_name, preset_name, scoring_data, record_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, browser_id, file_id, file_name, preset_name,
             scoring_json, record_count, now)
        )
        conn.commit()
    finally:
        conn.close()
    
    return session_id


def get_sessions(browser_id: str) -> List[Dict[str, Any]]:
    """
    Возвращает метаданные всех сессий для данного browser_id.
    Без scoring_data (слишком тяжёлый) — только id, file_name, preset, дата, кол-во записей.
    Отсортировано по дате (новые первые).
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """SELECT id, file_id, file_name, preset_name, record_count, created_at
               FROM sessions
               WHERE browser_id = ?
               ORDER BY created_at DESC""",
            (browser_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_session_data(session_id: str, browser_id: str) -> Optional[Dict[str, Any]]:
    """
    Возвращает полные данные сессии (включая scoring_data) по ID.
    Проверяет принадлежность к browser_id для минимальной изоляции.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND browser_id = ?",
            (session_id, browser_id)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        result = dict(row)
        result["scoring_data"] = json.loads(result["scoring_data"])
        return result
    finally:
        conn.close()


def delete_session(session_id: str, browser_id: str) -> bool:
    """Удаляет сессию. Возвращает True если сессия была найдена и удалена."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE id = ? AND browser_id = ?",
            (session_id, browser_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def cleanup_old_sessions(days: int = SESSION_TTL_DAYS) -> int:
    """
    Удаляет сессии старше указанного количества дней.
    Возвращает количество удалённых записей.
    Можно вызывать при старте сервера или по расписанию.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE created_at < ?",
            (cutoff,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
