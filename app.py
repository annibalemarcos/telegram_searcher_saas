import asyncio
import csv
import io
import json
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, Response, redirect, url_for
from flask import Response

from telegram_group_searcher import TelegramGroupSearcher, API_ID, API_HASH

APP_PORT = 5888
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "history.db")

app = Flask(__name__)
app.config["LAST_RESULTS"] = []
app.config["LAST_DEBUG"] = {}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            phone TEXT,
            keyword TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            raw_count INTEGER DEFAULT 0,
            filtered_count INTEGER DEFAULT 0,
            debug_json TEXT DEFAULT '{}',
            results_json TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    conn.close()


def save_search(phone, keyword, results, debug):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO searches (
            created_at, phone, keyword, result_count,
            raw_count, filtered_count, debug_json, results_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        created_at,
        phone,
        keyword,
        len(results),
        debug.get("raw_count", 0),
        debug.get("filtered_count", 0),
        json.dumps(debug, ensure_ascii=False, default=str),
        json.dumps(results, ensure_ascii=False, default=str)
    ))
    search_id = cur.lastrowid
    conn.commit()
    conn.close()
    return search_id


def get_history(limit=12):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, created_at, keyword, result_count, raw_count, filtered_count
        FROM searches
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_search(search_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM searches WHERE id = ?", (search_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["debug"] = json.loads(item.get("debug_json") or "{}")
    item["results"] = json.loads(item.get("results_json") or "[]")
    return item


def safe_int(value, default=None):
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except Exception:
        return default


def make_debug_summary(keyword, phone, raw, filtered, filters, warnings, started_at, finished_at):
    raw_count = len(raw or [])
    filtered_count = len(filtered or [])

    excluded_count = max(raw_count - filtered_count, 0)
    search_methods = {}
    type_counts = {}

    for g in raw or []:
        method = g.get("method") or "unknown"
        search_methods[method] = search_methods.get(method, 0) + 1
        gtype = g.get("type") or "unknown"
        type_counts[gtype] = type_counts.get(gtype, 0) + 1

    return {
        "keyword": keyword,
        "phone": phone,
        "started_at": started_at,
        "finished_at": finished_at,
        "raw_count": raw_count,
        "filtered_count": filtered_count,
        "excluded_count": excluded_count,
        "filters": filters,
        "warnings": warnings,
        "search_methods": search_methods,
        "type_counts": type_counts,
        "status": "ok" if filtered_count > 0 else "empty",
    }


@app.route("/", methods=["GET", "POST"])
def dashboard():
    results = []
    debug_info = app.config.get("LAST_DEBUG", {})
    selected_search_id = request.args.get("search_id")
    current_phone = "+5519991979897"

    if selected_search_id:
        saved = get_search(selected_search_id)
        if saved:
            results = saved["results"]
            debug_info = saved["debug"]
            app.config["LAST_RESULTS"] = results
            app.config["LAST_DEBUG"] = debug_info

    if request.method == "POST":
        phone = request.form.get("phone", "+5519991979897").strip() or "+5519991979897"
        keyword = request.form.get("keyword", "").strip()
        current_phone = phone

        language = request.form.get("language") or None
        group_type = request.form.get("group_type") or "all"
        min_members = safe_int(request.form.get("min_members"), 0) or 0
        max_members = safe_int(request.form.get("max_members"), None)
        limit = safe_int(request.form.get("limit"), 50) or 50
        verified_only = request.form.get("verified_only") == "on"
        exclude_my_groups = request.form.get("exclude_my_groups") == "on"

        warnings = []
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        async def run_search():
            searcher = TelegramGroupSearcher(API_ID, API_HASH, phone)
            searcher.filters["language"] = language
            searcher.filters["group_type"] = group_type
            searcher.filters["min_members"] = min_members
            searcher.filters["max_members"] = max_members
            searcher.filters["verified_only"] = verified_only
            searcher.filters["exclude_my_groups"] = exclude_my_groups

            connected = await searcher.connect()
            if not connected:
                warnings.append("Falha ao conectar ao Telegram. Verifique sessão, telefone e autenticação.")
                return [], [], dict(searcher.filters)

            try:
                raw = await searcher.search_groups(keyword, limit=limit)
                filtered = await searcher.apply_filters(raw)
                return raw, filtered, dict(searcher.filters)
            except Exception as exc:
                warnings.append(f"Erro durante a busca: {exc}")
                return [], [], dict(searcher.filters)
            finally:
                await searcher.disconnect()

        if keyword:
            raw, results, active_filters = asyncio.run(run_search())
        else:
            raw, results, active_filters = [], [], {}

        finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        debug_info = make_debug_summary(
            keyword=keyword,
            phone=phone,
            raw=raw,
            filtered=results,
            filters=active_filters,
            warnings=warnings,
            started_at=started_at,
            finished_at=finished_at,
        )

        app.config["LAST_RESULTS"] = results
        app.config["LAST_DEBUG"] = debug_info

        save_search(phone, keyword or "(sem termo)", results, debug_info)

    return render_template(
        "dashboard.html",
        results=results,
        history=get_history(),
        debug_info=debug_info,
        current_phone=current_phone,
    )


@app.route("/history")
def history():
    return render_template(
        "history.html",
        history=get_history(100),
        debug_info=app.config.get("LAST_DEBUG", {}),
    )


@app.route("/debug")
def debug_page():
    return render_template(
        "debug.html",
        debug_info=app.config.get("LAST_DEBUG", {}),
        history=get_history(20),
    )


@app.route("/search/<int:search_id>")
def view_search(search_id):
    return redirect(url_for("dashboard", search_id=search_id) + "#debug")


@app.route("/export/csv")
def export_csv():
    results = app.config.get("LAST_RESULTS", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["title", "username", "participants_count", "type", "verified", "link"])
    for g in results:
        username = g.get("username") or ""
        writer.writerow([
            g.get("title", ""),
            username,
            g.get("participants_count", 0),
            g.get("type", ""),
            g.get("verified", False),
            f"https://t.me/{username}" if username else ""
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=resultados.csv"}
    )


@app.route("/export/json")
def export_json():
    results = app.config.get("LAST_RESULTS", [])
    return Response(
        json.dumps(results, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=resultados.json"}
    )


@app.route("/export/txt")
def export_txt():
    results = app.config.get("LAST_RESULTS", [])
    
    # 1. Definimos o cabeçalho para dar contexto ao ficheiro
    # O sinal :<40 significa "alinha à esquerda e ocupa 40 espaços"
    header = f"{'TÍTULO':<40} | {'USERNAME':<25} | {'MEMBROS':<10} | {'LINK'}"
    separator = "-" * len(header)
    
    lines = [header, separator]

    for g in results:
        # 2. Tratamento dos dados
        title = (g.get('title') or "Sem Título")[:38] # Corta títulos muito longos
        username = g.get("username") or "N/A"
        count = str(g.get('participants_count', 0))
        link = f"https://t.me/{username}" if g.get("username") else "N/A"

        # 3. Formatação da linha com colunas fixas
        line = f"{title:<40} | {username:<25} | {count:<10} | {link}"
        lines.append(line)

    # 4. Retorno do ficheiro formatado
    return Response(
        "\n".join(lines),
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment;filename=resultados.txt"}
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=APP_PORT)
