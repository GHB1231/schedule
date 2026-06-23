"""
数据库层 — SQLite 数据库初始化与基本操作
"""
import os
import sqlite3
from datetime import datetime
from typing import Optional

from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 使查询结果支持字典式访问
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_type  TEXT NOT NULL DEFAULT 'other',
            start_time  TEXT NOT NULL,
            end_time    TEXT,
            location    TEXT DEFAULT '',
            priority    INTEGER DEFAULT 0,
            tags        TEXT DEFAULT '[]',
            source      TEXT DEFAULT 'manual',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS learning_samples (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_input      TEXT NOT NULL,
            parsed_result  TEXT NOT NULL DEFAULT '{}',
            user_correction TEXT,
            is_correct     INTEGER DEFAULT 0,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS job_info (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            title       TEXT DEFAULT '',
            description TEXT DEFAULT '',
            deadline    TEXT DEFAULT '',
            url         TEXT DEFAULT '',
            source      TEXT DEFAULT '',
            is_applied  INTEGER DEFAULT 0,
            fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_preferences (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT UNIQUE NOT NULL,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS time_preferences (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type          TEXT NOT NULL,
            preferred_start_hour INTEGER,
            preferred_day_of_week INTEGER,
            confidence          REAL DEFAULT 0.0,
            sample_count        INTEGER DEFAULT 0,
            updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()


# ============ 事件 CRUD ============

def insert_event(event: dict) -> int:
    """插入事件，返回 ID"""
    conn = get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO events (title, description, event_type, start_time, end_time,
           location, priority, tags, source, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["title"],
            event.get("description", ""),
            event.get("event_type", "other"),
            event["start_time"],
            event.get("end_time"),
            event.get("location", ""),
            event.get("priority", 0),
            event.get("tags", "[]"),
            event.get("source", "manual"),
            now,
            now,
        ),
    )
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    return event_id


def update_event(event_id: int, updates: dict) -> bool:
    """更新事件"""
    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [event_id]
    conn = get_connection()
    conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def delete_event(event_id: int) -> bool:
    """删除事件"""
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return True


def get_event(event_id: int) -> Optional[dict]:
    """获取单个事件"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_events_in_range(start_date: str, end_date: str) -> list[dict]:
    """获取指定时间范围内的事件"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM events
           WHERE start_time >= ? AND start_time < ?
           ORDER BY start_time ASC""",
        (start_date, end_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_events() -> list[dict]:
    """获取所有事件"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM events ORDER BY start_time DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 学习样本 CRUD ============

def insert_sample(raw_input: str, parsed_result: dict) -> int:
    """插入学习样本，返回 ID"""
    conn = get_connection()
    import json
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO learning_samples (raw_input, parsed_result, created_at) VALUES (?, ?, ?)",
        (raw_input, json.dumps(parsed_result, ensure_ascii=False), now),
    )
    conn.commit()
    sid = cursor.lastrowid
    conn.close()
    return sid


def update_sample(sample_id: int, correction: dict, is_correct: bool = False):
    """更新学习样本的修正信息"""
    import json
    conn = get_connection()
    conn.execute(
        "UPDATE learning_samples SET user_correction = ?, is_correct = ? WHERE id = ?",
        (json.dumps(correction, ensure_ascii=False), int(is_correct), sample_id),
    )
    conn.commit()
    conn.close()


def get_all_samples() -> list[dict]:
    """获取所有学习样本"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM learning_samples ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_corrected_samples() -> list[dict]:
    """获取所有包含用户修正的样本"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM learning_samples WHERE user_correction IS NOT NULL ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sample_count() -> int:
    """获取样本总数"""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM learning_samples").fetchone()
    conn.close()
    return row["cnt"] if row else 0


# ============ 校招信息 CRUD ============

def insert_job_info(info: dict) -> int:
    """插入校招信息，返回 ID"""
    conn = get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO job_info (company, title, description, deadline, url, source, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            info["company"],
            info.get("title", ""),
            info.get("description", ""),
            info.get("deadline", ""),
            info.get("url", ""),
            info.get("source", ""),
            now,
        ),
    )
    conn.commit()
    jid = cursor.lastrowid
    conn.close()
    return jid


def get_job_info(company: str = None, days: int = 30) -> list[dict]:
    """获取校招信息（可按企业筛选、按时间范围过滤）"""
    conn = get_connection()
    if company:
        rows = conn.execute(
            """SELECT * FROM job_info WHERE company = ?
               ORDER BY fetched_at DESC LIMIT 50""",
            (company,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM job_info ORDER BY fetched_at DESC LIMIT 100"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_info_recent(days: int = 7) -> list[dict]:
    """获取最近的校招信息"""
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT * FROM job_info
            WHERE fetched_at >= datetime('now', '-{days} days')
            ORDER BY fetched_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 时间偏好 CRUD ============

def upsert_time_preference(pref: dict):
    """插入或更新时间偏好"""
    conn = get_connection()
    now = datetime.now().isoformat()

    event_type = pref["event_type"]
    start_hour = pref.get("preferred_start_hour")
    day_of_week = pref.get("preferred_day_of_week")

    # 查询是否已存在
    row = conn.execute(
        """SELECT id FROM time_preferences
           WHERE event_type = ? AND preferred_start_hour IS ? AND preferred_day_of_week IS ?""",
        (event_type, start_hour, day_of_week),
    ).fetchone()

    if row:
        conn.execute(
            """UPDATE time_preferences
               SET confidence = ?, sample_count = ?, updated_at = ?
               WHERE id = ?""",
            (pref.get("confidence", 0.0), pref.get("sample_count", 0), now, row["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO time_preferences
               (event_type, preferred_start_hour, preferred_day_of_week, confidence, sample_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, start_hour, day_of_week,
             pref.get("confidence", 0.0), pref.get("sample_count", 0), now),
        )

    conn.commit()
    conn.close()


def get_time_preferences(event_type: str = None) -> list[dict]:
    """获取时间偏好"""
    conn = get_connection()
    if event_type:
        rows = conn.execute(
            "SELECT * FROM time_preferences WHERE event_type = ? ORDER BY confidence DESC",
            (event_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM time_preferences ORDER BY event_type, confidence DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 用户偏好 ============

def set_preference(key: str, value: str):
    """设置用户偏好"""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, value, now),
    )
    conn.commit()
    conn.close()


def get_preference(key: str, default: str = None) -> Optional[str]:
    """获取用户偏好"""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM user_preferences WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default
