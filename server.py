import csv
import io
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory, g, Response

ROOT = Path(__file__).resolve().parent
# Allow overriding DB path via env for Docker persistence
DB_PATH = Path(os.environ.get("DATABASE_PATH") or (ROOT / "finance.db"))

app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS incomes (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            source TEXT,
            processor TEXT,
            amount REAL DEFAULT 0,
            fees REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            category TEXT,
            seller TEXT,
            items TEXT,
            order_number TEXT,
            total REAL DEFAULT 0,
            notes TEXT,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payroll (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            employee TEXT NOT NULL,
            amount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()


def generate_id() -> str:
    return uuid4().hex


RESOURCE_CONFIG = {
    "income": {
        "table": "incomes",
        "columns": ["id", "date", "source", "processor", "amount", "fees", "notes"],
        "to_db": lambda payload: {
            "id": str(payload.get("id") or generate_id()),
            "date": (payload.get("date") or "").strip(),
            "source": (payload.get("source") or "").strip(),
            "processor": (payload.get("processor") or "").strip(),
            "amount": float(payload.get("amount") or 0),
            "fees": float(payload.get("fees") or 0),
            "notes": (payload.get("notes") or "").strip(),
        },
        "from_db": lambda row: {
            "id": row["id"],
            "date": row["date"],
            "source": row["source"] or "",
            "processor": row["processor"] or "",
            "amount": float(row["amount"] or 0),
            "fees": float(row["fees"] or 0),
            "notes": row["notes"] or "",
        },
        "csv_header": ["Date", "Source", "Processor", "AmountGBP", "FeesGBP", "Notes"],
        "csv_row": lambda rec: [
            rec["date"],
            rec["source"],
            rec["processor"],
            f'{rec["amount"]:.2f}',
            f'{rec["fees"]:.2f}',
            rec["notes"],
        ],
    },
    "expenses": {
        "table": "expenses",
        "columns": [
            "id",
            "date",
            "category",
            "seller",
            "items",
            "order_number",
            "total",
            "notes",
            "source",
        ],
        "to_db": lambda payload: {
            "id": str(payload.get("id") or generate_id()),
            "date": (payload.get("date") or "").strip(),
            "category": (payload.get("category") or "").strip(),
            "seller": (payload.get("seller") or "").strip(),
            "items": (payload.get("items") or "").strip(),
            "order_number": (payload.get("orderNumber") or payload.get("order_number") or "").strip(),
            "total": float(payload.get("total") or payload.get("price") or 0),
            "notes": (payload.get("notes") or "").strip(),
            "source": (payload.get("source") or "").strip(),
        },
        "from_db": lambda row: {
            "id": row["id"],
            "date": row["date"],
            "category": row["category"] or "",
            "seller": row["seller"] or "",
            "items": row["items"] or "",
            "orderNumber": row["order_number"] or "",
            "total": float(row["total"] or 0),
            "notes": row["notes"] or "",
            "source": row["source"] or "",
        },
        "csv_header": ["Date", "Category", "Seller", "Item(s)", "Order #", "TotalGBP", "Notes", "Source"],
        "csv_row": lambda rec: [
            rec["date"],
            rec["category"],
            rec["seller"],
            rec["items"],
            rec["orderNumber"],
            f'{rec["total"]:.2f}',
            rec["notes"],
            rec["source"],
        ],
    },
    "payroll": {
        "table": "payroll",
        "columns": ["id", "date", "employee", "amount", "notes"],
        "to_db": lambda payload: {
            "id": str(payload.get("id") or generate_id()),
            "date": (payload.get("date") or "").strip(),
            "employee": (payload.get("employee") or "").strip(),
            "amount": float(payload.get("amount") or 0),
            "notes": (payload.get("notes") or "").strip(),
        },
        "from_db": lambda row: {
            "id": row["id"],
            "date": row["date"],
            "employee": row["employee"] or "",
            "amount": float(row["amount"] or 0),
            "notes": row["notes"] or "",
        },
        "csv_header": ["Date", "Employee", "AmountGBP", "Notes"],
        "csv_row": lambda rec: [
            rec["date"],
            rec["employee"],
            f'{rec["amount"]:.2f}',
            rec["notes"],
        ],
    },
}


with app.app_context():
    init_db()


def list_records(kind: str):
    config = RESOURCE_CONFIG[kind]
    db = get_db()
    rows = db.execute(
        f"SELECT {', '.join(config['columns'])} FROM {config['table']} ORDER BY date DESC, updated_at DESC"
    ).fetchall()
    return [config["from_db"](row) for row in rows]


def get_record(kind: str, record_id: str):
    config = RESOURCE_CONFIG[kind]
    db = get_db()
    row = db.execute(
        f"SELECT {', '.join(config['columns'])} FROM {config['table']} WHERE id = ?",
        (record_id,),
    ).fetchone()
    return config["from_db"](row) if row else None


def upsert_record(kind: str, payload: dict):
    config = RESOURCE_CONFIG[kind]
    row_data = config["to_db"](payload or {})
    if not row_data["date"]:
        raise ValueError("date is required")
    if kind == "payroll" and not row_data["employee"]:
        raise ValueError("employee is required")

    columns = config["columns"]
    assignments = ", ".join(f"{col}=excluded.{col}" for col in columns if col != "id")
    placeholders = ", ".join(f":{col}" for col in columns)

    db = get_db()
    db.execute(
        f"""INSERT INTO {config['table']} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {assignments}, updated_at=CURRENT_TIMESTAMP""",
        row_data,
    )
    db.commit()
    return get_record(kind, row_data["id"])


def delete_record(kind: str, record_id: str):
    config = RESOURCE_CONFIG[kind]
    db = get_db()
    result = db.execute(
        f"DELETE FROM {config['table']} WHERE id = ?",
        (record_id,),
    )
    db.commit()
    return result.rowcount > 0


def clear_records(kind: str):
    config = RESOURCE_CONFIG[kind]
    db = get_db()
    db.execute(f"DELETE FROM {config['table']}")
    db.commit()


def export_csv(kind: str) -> str:
    config = RESOURCE_CONFIG[kind]
    records = list_records(kind)
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(config["csv_header"])
    for record in records:
        writer.writerow(config["csv_row"](record))
    return output.getvalue()


@app.route("/api/version")
def version():
    ver = os.environ.get("APP_VERSION", "dev")
    return jsonify({"version": ver})


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/ping")
def ping():
    db = get_db()
    counts = {
        kind: db.execute(f"SELECT COUNT(*) FROM {config['table']}").fetchone()[0]
        for kind, config in RESOURCE_CONFIG.items()
    }
    return jsonify({"ok": True, "counts": counts})


@app.route("/api/<kind>.csv")
def download_csv(kind):
    if kind not in RESOURCE_CONFIG:
        return jsonify({"error": "Unknown resource"}), 404
    csv_text = export_csv(kind)
    filename = f"{kind}-{request.args.get('date', '') or 'export'}.csv"
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/<kind>", methods=["GET", "POST", "DELETE"])
def collection(kind):
    if kind not in RESOURCE_CONFIG:
        return jsonify({"error": "Unknown resource"}), 404

    if request.method == "GET":
        return jsonify(list_records(kind))

    if request.method == "POST":
        try:
            data = request.get_json(force=True, silent=False) or {}
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400
        try:
            stored = upsert_record(kind, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(stored)

    if request.method == "DELETE":
        clear_records(kind)
        return jsonify({"cleared": True})

    return jsonify({"error": "Unsupported method"}), 405


@app.route("/api/<kind>/<record_id>", methods=["GET", "PUT", "DELETE"])
def resource_detail(kind, record_id):
    if kind not in RESOURCE_CONFIG:
        return jsonify({"error": "Unknown resource"}), 404

    if request.method == "GET":
        record = get_record(kind, record_id)
        if not record:
            return jsonify({"error": "Not found"}), 404
        return jsonify(record)

    if request.method == "DELETE":
        deleted = delete_record(kind, record_id)
        return (jsonify({"deleted": True}), 200) if deleted else (jsonify({"error": "Not found"}), 404)

    if request.method == "PUT":
        try:
            payload = request.get_json(force=True, silent=False) or {}
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400
        payload["id"] = record_id
        try:
            stored = upsert_record(kind, payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(stored)

    return jsonify({"error": "Unsupported method"}), 405


@app.route("/")
def root():
    return send_from_directory(ROOT, "financial_summary.html")


@app.route("/<path:filename>")
def static_files(filename):
    file_path = ROOT / filename
    if not file_path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(ROOT, filename)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=False)
