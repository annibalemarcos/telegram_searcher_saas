import asyncio
import csv
import io
import json
import os
from dataclasses import asdict

from dotenv import load_dotenv
from flask import Flask, Response, flash, redirect, render_template, request, url_for

from core.db import get_results, init_db, recent_searches, save_search
from core.searcher import SearchFilters, run_telegram_search

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

API_ID = int(os.getenv("TELEGRAM_API_ID", "20041297"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "ba389b89510d524e1f62da82cc24c266")

init_db()


def bool_form(name: str, default: bool = False) -> bool:
    if name not in request.form:
        return default
    return request.form.get(name) in {"1", "true", "on", "yes"}


def int_or_none(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    stats = None
    current = {
        "phone": "+5519991979897",
        "keyword": "",
        "language": "",
        "min_members": "0",
        "max_members": "",
        "group_type": "all",
        "verified_only": False,
        "exclude_my_groups": True,
        "limit": "50",
    }

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        keyword = request.form.get("keyword", "").strip()
        current.update({k: request.form.get(k, current.get(k, "")) for k in current.keys() if k not in {"verified_only", "exclude_my_groups"}})
        current["verified_only"] = bool_form("verified_only")
        current["exclude_my_groups"] = bool_form("exclude_my_groups")

        if not phone or not keyword:
            flash("Telefone e termo de busca são obrigatórios.", "danger")
            return redirect(url_for("index"))

        filters = SearchFilters(
            language=request.form.get("language", "").strip(),
            min_members=int_or_none(request.form.get("min_members")) or 0,
            max_members=int_or_none(request.form.get("max_members")),
            group_type=request.form.get("group_type", "all"),
            verified_only=bool_form("verified_only"),
            exclude_my_groups=bool_form("exclude_my_groups"),
            limit=max(10, min(int_or_none(request.form.get("limit")) or 50, 100)),
        )

        try:
            results, stats = asyncio.run(run_telegram_search(API_ID, API_HASH, phone, keyword, filters))
            sid = save_search(phone, keyword, asdict(filters), stats, results)
            current["last_search_id"] = sid
            if not results:
                flash("Nenhum resultado retornado. Veja o painel de debug: ele mostra se o Telegram achou algo e onde foi filtrado.", "warning")
        except Exception as exc:
            flash(f"Erro ao buscar: {exc}", "danger")

    return render_template("index.html", results=results, stats=stats, recent=recent_searches(12), current=current)


@app.route("/history/<int:search_id>")
def history_detail(search_id):
    rows = get_results(search_id)
    return render_template("history.html", rows=rows, search_id=search_id)


@app.route("/export/<int:search_id>/<fmt>")
def export_results(search_id, fmt):
    rows = get_results(search_id)
    data = [dict(r) for r in rows]
    if fmt == "json":
        return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=telegram_results_{search_id}.json"})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["title", "username", "link", "participants_count", "type", "verified", "method", "is_mine", "description"])
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=telegram_results_{search_id}.csv"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5878, debug=True)
