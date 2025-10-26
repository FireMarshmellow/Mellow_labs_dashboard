import csv
import io
import os
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory, g, Response
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
# Allow overriding DB path via env for Docker persistence
DB_PATH = Path(os.environ.get("DATABASE_PATH") or (ROOT / "finance.db"))
UPLOAD_DIR = Path(os.environ.get("UPLOADS_DIR") or (ROOT / "uploads"))

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
            paid_from TEXT,
            delivery_fee REAL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('income','expenses')),
            record_id TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT,
            size INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_attachments_kind_record ON attachments(kind, record_id);
        """
    )
    db.commit()
    # Migrations for existing databases
    try:
        cols = {r[1] for r in db.execute("PRAGMA table_info(expenses)").fetchall()}
        if "paid_from" not in cols:
            db.execute("ALTER TABLE expenses ADD COLUMN paid_from TEXT")
        if "delivery_fee" not in cols:
            db.execute("ALTER TABLE expenses ADD COLUMN delivery_fee REAL DEFAULT 0")
        db.commit()
    except Exception:
        pass
    try:
        db.execute(
            "UPDATE expenses SET paid_from = ? WHERE paid_from IS NULL OR paid_from = ''",
            ("Tomasz Burzy Personal",),
        )
        db.execute(
            "UPDATE expenses SET delivery_fee = 0 WHERE delivery_fee IS NULL",
        )
        db.commit()
    except Exception:
        pass
    # Ensure upload base directory exists
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def generate_id() -> str:
    return uuid4().hex


def _ensure_record_dir(kind: str, record_id: str) -> Path:
    path = UPLOAD_DIR / kind / record_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _remove_record_dir(kind: str, record_id: str):
    path = UPLOAD_DIR / kind / record_id
    if path.exists() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _attachment_row_to_dict(row: sqlite3.Row) -> dict:
    if not row:
        return None
    rel_path = f"uploads/{row['kind']}/{row['record_id']}/{row['stored_name']}"
    return {
        "id": row["id"],
        "kind": row["kind"],
        "recordId": row["record_id"],
        "name": row["original_name"],
        "mime": row["mime_type"] or "",
        "size": int(row["size"] or 0),
        "url": f"/{rel_path}",
        "createdAt": row["created_at"],
    }


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
            "paid_from",
            "delivery_fee",
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
            "paid_from": (payload.get("paidFrom") or payload.get("paid_from") or "").strip(),
            "delivery_fee": float(payload.get("deliveryFee") or payload.get("delivery_fee") or 0),
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
            "paidFrom": row["paid_from"] or "",
            "deliveryFee": float(row["delivery_fee"] or 0),
        },
        "csv_header": ["Date", "Category", "Seller", "Item(s)", "Order #", "TotalGBP", "DeliveryFeeGBP", "Notes", "Source", "Paid From"],
        "csv_row": lambda rec: [
            rec["date"],
            rec["category"],
            rec["seller"],
            rec["items"],
            rec["orderNumber"],
            f'{rec["total"]:.2f}',
            f'{float(rec.get("deliveryFee", 0) or 0):.2f}',
            rec["notes"],
            rec["source"],
            rec.get("paidFrom", ""),
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


def list_attachments(kind: str, record_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT id, kind, record_id, original_name, stored_name, mime_type, size, created_at FROM attachments WHERE kind = ? AND record_id = ? ORDER BY created_at DESC",
        (kind, record_id),
    ).fetchall()
    return [_attachment_row_to_dict(r) for r in rows]


def create_attachments(kind: str, record_id: str, files) -> list:
    saved = []
    if not files:
        return saved
    record_dir = _ensure_record_dir(kind, record_id)
    db = get_db()
    for fs in files:
        if not fs or not getattr(fs, "filename", ""):
            continue
        original = fs.filename
        safe = secure_filename(original) or "file"
        stored = f"{uuid4().hex}_{safe}"
        dst = record_dir / stored
        fs.save(dst)
        try:
            size = dst.stat().st_size
        except Exception:
            size = 0
        att_id = uuid4().hex
        db.execute(
            """
            INSERT INTO attachments (id, kind, record_id, original_name, stored_name, mime_type, size)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (att_id, kind, record_id, original, stored, getattr(fs, "mimetype", None), size),
        )
        saved.append(
            {
                "id": att_id,
                "kind": kind,
                "recordId": record_id,
                "name": original,
                "mime": getattr(fs, "mimetype", "") or "",
                "size": int(size),
                "url": f"/uploads/{kind}/{record_id}/{stored}",
            }
        )
    db.commit()
    return saved


def get_attachment(att_id: str):
    db = get_db()
    row = db.execute(
        "SELECT id, kind, record_id, original_name, stored_name, mime_type, size, created_at FROM attachments WHERE id = ?",
        (att_id,),
    ).fetchone()
    return row


def delete_attachment(att_id: str) -> bool:
    row = get_attachment(att_id)
    if not row:
        return False
    # attempt to delete file from disk
    try:
        file_path = UPLOAD_DIR / row["kind"] / row["record_id"] / row["stored_name"]
        if file_path.exists():
            file_path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass
    db = get_db()
    res = db.execute("DELETE FROM attachments WHERE id = ?", (att_id,))
    db.commit()
    return res.rowcount > 0


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
    deleted = result.rowcount > 0
    # If a record was deleted, also remove its attachments (DB + files)
    if deleted and kind in ("income", "expenses"):
        _remove_record_dir(kind, record_id)
        db.execute("DELETE FROM attachments WHERE kind = ? AND record_id = ?", (kind, record_id))
    db.commit()
    return deleted


def clear_records(kind: str):
    config = RESOURCE_CONFIG[kind]
    db = get_db()
    db.execute(f"DELETE FROM {config['table']}")
    if kind in ("income", "expenses"):
        db.execute("DELETE FROM attachments WHERE kind = ?", (kind,))
        shutil.rmtree(UPLOAD_DIR / kind, ignore_errors=True)
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




"""Factory reset helpers"""


def factory_reset():
    db = get_db()
    for cfg in RESOURCE_CONFIG.values():
        db.execute(f"DELETE FROM {cfg['table']}")
    db.execute("DELETE FROM attachments")
    db.commit()
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/api/factory-reset", methods=["POST"])
def api_factory_reset():
    payload = request.get_json(silent=True) or {}
    if not payload.get("confirm"):
        return jsonify({"error": "Confirmation required"}), 400
    factory_reset()
    return jsonify({"reset": True})


@app.route("/api/version")
def version():
    ver = os.environ.get("APP_VERSION", "dev")
    return jsonify({"version": ver})


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return ("", 204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept",
    })


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


@app.route("/api/<kind>/<record_id>/attachments", methods=["GET", "POST"])
def attachments_collection(kind, record_id):
    if kind not in ("income", "expenses"):
        return jsonify({"error": "Unsupported kind for attachments"}), 400
    # Ensure record exists
    rec = get_record(kind, record_id)
    if not rec:
        return jsonify({"error": "Parent record not found"}), 404
    if request.method == "GET":
        return jsonify(list_attachments(kind, record_id))
    # POST: upload files via multipart form
    if not request.files:
        return jsonify({"error": "No files uploaded"}), 400
    files = request.files.getlist("files") or []
    saved = create_attachments(kind, record_id, files)
    return jsonify(saved)


@app.route("/api/attachments/<att_id>", methods=["GET", "DELETE"])
def attachments_detail(att_id):
    row = get_attachment(att_id)
    if not row:
        return jsonify({"error": "Not found"}), 404
    if request.method == "GET":
        return jsonify(_attachment_row_to_dict(row))
    # DELETE
    ok = delete_attachment(att_id)
    return (jsonify({"deleted": True}), 200) if ok else (jsonify({"error": "Not found"}), 404)


@app.route("/api/attachments/<att_id>/download")
def attachments_download(att_id):
    row = get_attachment(att_id)
    if not row:
        return jsonify({"error": "Not found"}), 404
    folder = UPLOAD_DIR / row["kind"] / row["record_id"]
    filename = row["stored_name"]
    # return with original filename hint
    resp = send_from_directory(folder, filename)
    try:
        disp = f"inline; filename={row['original_name']}"
        resp.headers["Content-Disposition"] = disp
    except Exception:
        pass
    return resp


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
