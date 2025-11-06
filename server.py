import base64
import csv
import io
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory, g, Response
import requests
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

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
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


def get_all_settings() -> dict:
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default=None):
    if not key:
        return default
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value):
    if not key:
        raise ValueError("Setting key required")
    db = get_db()
    if value is None:
        db.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        text = str(value)
        if text.strip() == "":
            db.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, text),
            )
    db.commit()


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                parts.append(text)
        return ", ".join(parts)
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            if val is None:
                continue
            text = str(val).strip()
            if not text:
                continue
            parts.append(f"{key}: {text}")
        return ", ".join(parts)
    return str(value).strip()


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        snippet = match.group(0)
        try:
            data = json.loads(snippet)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise ValueError("Model response was not valid JSON")


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    normal = text.replace("Z", "")
    try:
        dt = datetime.fromisoformat(normal)
        return dt.date().isoformat()
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    # Attempt YYYYMMDD or DDMMYYYY style strings
    match = re.search(r"(\d{4})[^\d]?(\d{1,2})[^\d]?(\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"(\d{1,2})[^\d]?(\d{1,2})[^\d]?(\d{2,4})", text)
    if match:
        year = int(match.group(3))
        if year < 100:
            year += 2000 if year < 50 else 1900
        try:
            return datetime(year, int(match.group(1)), int(match.group(2))).date().isoformat()
        except ValueError:
            pass
    return ""


def _coerce_amount(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace(",", "")
    match = re.findall(r"-?\d+(?:\.\d+)?", text)
    if match:
        try:
            return float(match[-1])
        except ValueError:
            pass
    filtered = re.sub(r"[^\d\.\-]", "", text)
    try:
        return float(filtered)
    except ValueError:
        return 0.0


def get_attachment(att_id: str):
    db = get_db()
    row = db.execute(
        "SELECT id, kind, record_id, original_name, stored_name, mime_type, size, created_at FROM attachments WHERE id = ?",
        (att_id,),
    ).fetchone()
    return row


def get_attachment_by_storage(kind: str, record_id: str, stored_name: str):
    db = get_db()
    row = db.execute(
        """
        SELECT id, kind, record_id, original_name, stored_name, mime_type, size, created_at
        FROM attachments
        WHERE kind = ? AND record_id = ? AND stored_name = ?
        """,
        (kind, record_id, stored_name),
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
    db.execute("DELETE FROM settings")
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


@app.route("/api/settings", methods=["GET"])
def api_settings():
    return jsonify({"settings": get_all_settings()})


@app.route("/api/settings/<key>", methods=["GET", "PUT", "DELETE"])
def api_setting_detail(key):
    norm_key = (key or "").strip()
    if not norm_key:
        return jsonify({"error": "Invalid key"}), 400
    if request.method == "GET":
        value = get_setting(norm_key, "")
        return jsonify({"key": norm_key, "value": value or ""})
    if request.method == "DELETE":
        set_setting(norm_key, None)
        return jsonify({"key": norm_key, "value": ""})
    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "Missing value"}), 400
    set_setting(norm_key, payload.get("value"))
    return jsonify({"key": norm_key, "value": get_setting(norm_key, "") or ""})


@app.route("/api/expenses/scan", methods=["POST"])
def api_expense_scan():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    upload = request.files["file"]
    if not upload or not upload.filename:
        return jsonify({"error": "No file uploaded"}), 400

    llm_base = (get_setting("llm_base_url") or "").strip()
    if not llm_base:
        return jsonify({"error": "Configure the LLM endpoint in Settings first."}), 400
    model_name = (get_setting("llm_model") or "").strip() or "receipt-parser"
    api_key = (get_setting("llm_api_key") or "").strip()

    raw_bytes = upload.read()
    if not raw_bytes:
        return jsonify({"error": "Uploaded file was empty."}), 400

    mime = upload.mimetype or "image/jpeg"
    encoded_image = base64.b64encode(raw_bytes).decode("ascii")

    endpoint = llm_base.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    system_prompt = (
        "You extract structured data from receipts and invoices. "
        "Always respond with a strict JSON object containing the fields: "
        "date (YYYY-MM-DD), category, seller, items, orderNumber, total, deliveryFee, notes, "
        "source, paidFrom. Use empty strings when information is missing. "
        "For totals use numbers (no currency symbols)."
    )
    user_prompt = (
        "Read the supplied receipt image and return the JSON object with the required fields. "
        "Do not include any explanation or text outside the JSON."
    )
    payload_style = (get_setting("llm_payload_style", "auto") or "auto").strip().lower() or "auto"
    style = payload_style
    if style == "auto":
        base_lower = llm_base.lower()
        if any(tag in base_lower for tag in ("dashscope", "qwen", "aliyun")):
            style = "qwen"
        else:
            style = "openai"

    if style == "qwen":
        user_blocks = [
            {"type": "input_text", "text": user_prompt},
            {"type": "input_image", "image": encoded_image},
        ]
    else:
        # Default to OpenAI-compatible payload
        user_blocks = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded_image}"}},
        ]

    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_blocks},
        ],
        "temperature": 0.1,
    }

    try:
        llm_response = requests.post(endpoint, headers=headers, json=body, timeout=60)
        llm_response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Failed to contact LLM endpoint: {exc}"}), 502

    try:
        payload = llm_response.json()
    except ValueError:
        return jsonify({"error": "LLM response was not valid JSON payload"}), 502

    message_text = ""
    if isinstance(payload, dict):
        choices = payload.get("choices") or []
        if choices:
            message_text = choices[0].get("message", {}).get("content") or ""
    if not message_text:
        return jsonify({"error": "LLM did not return any content"}), 502

    try:
        extracted = _extract_json_object(message_text)
    except ValueError as exc:
        return jsonify({"error": str(exc), "raw": message_text}), 502

    normalized_payload = {
        "date": _normalize_date(
            extracted.get("date")
            or extracted.get("purchase_date")
            or extracted.get("transaction_date")
            or extracted.get("invoice_date")
        ),
        "category": (_stringify(extracted.get("category")) or "Imported") or "Imported",
        "seller": _stringify(
            extracted.get("seller") or extracted.get("merchant") or extracted.get("vendor")
        ),
        "items": _stringify(
            extracted.get("items")
            or extracted.get("lineItems")
            or extracted.get("description")
        ),
        "orderNumber": _stringify(
            extracted.get("orderNumber")
            or extracted.get("order_number")
            or extracted.get("invoiceNumber")
            or extracted.get("reference")
        ),
        "total": _coerce_amount(extracted.get("total") or extracted.get("amount")),
        "deliveryFee": _coerce_amount(
            extracted.get("deliveryFee") or extracted.get("delivery_fee") or 0
        ),
        "notes": _stringify(
            extracted.get("notes") or extracted.get("additionalNotes") or ""
        ),
        "source": _stringify(
            extracted.get("source") or extracted.get("paymentMethod") or ""
        ),
        "paidFrom": _stringify(
            extracted.get("paidFrom") or extracted.get("account") or ""
        ),
    }

    if not normalized_payload["date"]:
        return (
            jsonify(
                {
                    "error": "Model did not return a usable date.",
                    "suggested": normalized_payload,
                    "raw": extracted,
                }
            ),
            422,
        )
    if normalized_payload["total"] <= 0:
        return (
            jsonify(
                {
                    "error": "Model did not return a positive total amount.",
                    "suggested": normalized_payload,
                    "raw": extracted,
                }
            ),
            422,
        )

    try:
        stored = upsert_record("expenses", normalized_payload)
    except ValueError as exc:
        return (
            jsonify(
                {
                    "error": f"Failed to save record: {exc}",
                    "suggested": normalized_payload,
                    "raw": extracted,
                }
            ),
            400,
        )

    try:
        upload.stream.seek(0)
    except Exception:
        upload.stream = io.BytesIO(raw_bytes)
    attachments = create_attachments("expenses", stored["id"], [upload])

    return jsonify(
        {
            "expense": stored,
            "attachments": attachments,
            "extracted": extracted,
            "modelResponse": message_text,
        }
    )


@app.route("/uploads/<kind>/<record_id>/<filename>")
def serve_upload(kind, record_id, filename):
    if kind not in ("income", "expenses"):
        return jsonify({"error": "Not found"}), 404
    row = get_attachment_by_storage(kind, record_id, filename)
    if not row:
        return jsonify({"error": "Not found"}), 404
    base = UPLOAD_DIR.resolve()
    target = (base / kind / record_id / filename).resolve()
    if base not in target.parents:
        return jsonify({"error": "Not found"}), 404
    if not target.exists() or not target.is_file():
        return jsonify({"error": "Not found"}), 404
    resp = send_from_directory(target.parent, target.name)
    mime = row["mime_type"]
    if mime:
        resp.headers.setdefault("Content-Type", mime)
    try:
        resp.headers.setdefault("Content-Disposition", f"inline; filename={row['original_name']}")
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


# Ensure database schema exists whenever the module loads (e.g., under Gunicorn)
with app.app_context():
    init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=False)
