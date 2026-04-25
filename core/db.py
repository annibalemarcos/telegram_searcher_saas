import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "history.db"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                phone TEXT,
                keyword TEXT NOT NULL,
                result_count INTEGER NOT NULL DEFAULT 0,
                filters_json TEXT,
                stats_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL,
                title TEXT,
                username TEXT,
                link TEXT,
                participants_count INTEGER,
                type TEXT,
                verified INTEGER,
                method TEXT,
                is_mine INTEGER,
                description TEXT,
                FOREIGN KEY(search_id) REFERENCES searches(id)
            )
            """
        )


def save_search(phone: str, keyword: str, filters: Dict[str, Any], stats: Dict[str, Any], results: List[Dict[str, Any]]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO searches(phone, keyword, result_count, filters_json, stats_json) VALUES (?, ?, ?, ?, ?)",
            (phone, keyword, len(results), json.dumps(filters, ensure_ascii=False), json.dumps(stats, ensure_ascii=False)),
        )
        sid = int(cur.lastrowid)
        for g in results:
            conn.execute(
                """
                INSERT INTO results(search_id, title, username, link, participants_count, type, verified, method, is_mine, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid, g.get("title"), g.get("username"), g.get("link"), g.get("participants_count") or 0,
                    g.get("type"), 1 if g.get("verified") else 0, g.get("method"), 1 if g.get("is_mine") else 0,
                    g.get("description", ""),
                ),
            )
        return sid


def recent_searches(limit: int = 10):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM searches ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def get_results(search_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM results WHERE search_id = ? ORDER BY participants_count DESC", (search_id,)).fetchall()
