import json
import os
import tempfile
import uuid

import pandas as pd
from flask import Flask, abort, jsonify, request, send_from_directory

import parser as invoice_parser


OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
STRUCTURED_EXTS = {".csv", ".xlsx", ".xls"}

app = Flask(__name__, static_folder="static", static_url_path="/static")


def _parse_bool(val) -> bool:
    return str(val).lower() in ("1", "true", "yes", "on")


def _parse_json_dict(raw: str):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    allow_origin = origin if origin else "null"
    response.headers["Access-Control-Allow-Origin"] = allow_origin
    response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    requested_headers = request.headers.get("Access-Control-Request-Headers", "Content-Type,Authorization,Accept,Origin")
    response.headers["Access-Control-Allow-Headers"] = requested_headers
    if origin and origin != "null":
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/process", methods=["POST", "OPTIONS"])
def process_documents():
    if request.method == "OPTIONS":
        return ("", 204)
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded."}), 400

    custom_fields = _parse_json_dict(request.form.get("customFields", ""))
    vendor_categories = _parse_json_dict(request.form.get("categories", ""))
    force_ocr = _parse_bool(request.form.get("forceOcr", "false"))
    max_pages = int(request.form.get("maxPages", 5))

    records = []
    flat_rows = []
    temp_paths = []
    try:
        for file in files:
            suffix = os.path.splitext(file.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                file.save(tmp.name)
                temp_paths.append(tmp.name)
                ext = suffix.lower()
                if ext in STRUCTURED_EXTS:
                    table_rows, warn = _load_structured_rows(tmp.name, ext, custom_fields, vendor_categories)
                    record = _structured_record(file.filename, table_rows, warn)
                    records.append(record)
                    flat_rows.extend(table_rows)
                    continue

                text, warnings = invoice_parser.extract_text(tmp.name, force_ocr=force_ocr, max_pages=max_pages)
                if not text.strip():
                    warnings.append("No text detected; check OCR or source file.")
                parsed = invoice_parser.parse_invoice(text, custom_fields=custom_fields, vendor_categories=vendor_categories)
                parsed["source_file"] = file.filename
                parsed["warnings"] = warnings + parsed.get("warnings", [])
                records.append(parsed)
                flat_rows.extend(invoice_parser.flatten_for_export([parsed]))

        csv_name = f"invoices-{uuid.uuid4().hex[:8]}.csv"
        xlsx_name = f"invoices-{uuid.uuid4().hex[:8]}.xlsx"
        csv_path, xlsx_path = invoice_parser.export_rows(flat_rows, OUTPUT_DIR, csv_name, xlsx_name)

        response = {
            "records": records,
            "rows": flat_rows,
            "csv_url": f"/download/{csv_name}",
            "xlsx_url": f"/download/{xlsx_name}",
            "warnings": [w for r in records for w in r.get("warnings", [])],
        }
        return jsonify(response)
    finally:
        for path in temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass


def _load_structured_rows(path: str, ext: str, custom_fields, vendor_categories):
    warnings = []
    try:
        if ext == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)
    except Exception as exc:
        return [], [f"Failed to read structured file: {exc}"]

    if df.empty:
        warnings.append("Structured file contains no rows.")
        return [], warnings

    df = df.fillna("")
    rows = df.to_dict(orient="records")
    vendor_map = {k.lower(): v for k, v in vendor_categories.items()}
    for row in rows:
        # apply custom fields if not already present
        for k, v in custom_fields.items():
            row.setdefault(k, v)
        vendor_val = ""
        for key in ("vendor", "Vendor", "VENDOR"):
            if row.get(key):
                vendor_val = str(row.get(key))
                break
        if vendor_val and not row.get("category"):
            mapped = vendor_map.get(vendor_val.lower())
            if mapped:
                row["category"] = mapped
    return rows, warnings


def _structured_record(filename: str, rows, warnings):
    sample = rows[0] if rows else {}
    vendor = sample.get("vendor") or sample.get("Vendor") or sample.get("VENDOR") or "Structured data"
    date = sample.get("date") or sample.get("Date") or ""
    invoice_no = sample.get("invoice_number") or sample.get("Invoice") or sample.get("invoice") or ""
    payment = sample.get("payment_method") or sample.get("Payment") or ""
    total = _maybe_sum_column(rows, ["total", "Total", "amount", "Amount", "line_total", "lineTotal"])
    tax = _maybe_sum_column(rows, ["tax", "Tax"])
    summary_warning = "Structured file ingested; displaying raw rows."
    return {
        "source_file": filename,
        "vendor": vendor,
        "date": date,
        "time": sample.get("time") or "",
        "invoice_number": invoice_no,
        "payment_method": payment,
        "subtotal": _maybe_sum_column(rows, ["subtotal", "Subtotal"]),
        "tax": tax,
        "total": total,
        "category": sample.get("category") or "",
        "items": rows,
        "warnings": warnings + ([summary_warning] if rows else []),
    }


def _maybe_sum_column(rows, keys):
    for key in keys:
        vals = []
        for row in rows:
            if key in row:
                try:
                    vals.append(float(str(row[key]).replace(",", "")))
                except (TypeError, ValueError):
                    continue
        if vals:
            return round(sum(vals), 2)
    return ""


@app.get("/download/<path:filename>")
def download_file(filename: str):
    safe_name = os.path.basename(filename)
    file_path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
