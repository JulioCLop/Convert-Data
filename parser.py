import os
import re
from typing import Dict, List, Tuple

import pandas as pd
from tabulate import tabulate

try:
    import pdfplumber
except ImportError:  # pragma: no cover - handled at runtime
    pdfplumber = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled at runtime
    Image = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - handled at runtime
    pytesseract = None


DATE_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
    r"\b[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}\b",
]
TIME_PATTERN = r"\b\d{1,2}:\d{2}(?:\s?[APMapm]{2})?\b"
NUMBER_RE = re.compile(r"\$?\(?[-+]?\d+(?:[.,]\d+)?\)?")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}


def extract_text(path: str, force_ocr: bool = False, max_pages: int = 5) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        return _read_text_file(path), warnings
    if ext == ".pdf":
        text, warn = _extract_pdf(path, force_ocr=force_ocr, max_pages=max_pages)
        warnings.extend(warn)
        return text, warnings
    if ext in IMAGE_EXTS:
        text, warn = _extract_image(path)
        warnings.extend(warn)
        return text, warnings
    warnings.append(f"Unsupported extension '{ext}'; attempting plain text read.")
    return _read_text_file(path), warnings


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _extract_pdf(path: str, force_ocr: bool, max_pages: int) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    if pdfplumber is None:
        return "", ["pdfplumber not installed; cannot read PDF."]
    text_parts: List[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            pages = pdf.pages[:max_pages]
            for page in pages:
                if not force_ocr:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
                    continue
                ocr_text, warn = _ocr_pdf_page(page)
                if warn:
                    warnings.extend(warn)
                text_parts.append(ocr_text)
    except Exception as exc:  # pragma: no cover - runtime safety
        warnings.append(f"Failed to read PDF: {exc}")
    return "\n".join(text_parts), warnings


def _ocr_pdf_page(page) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    if pytesseract is None or Image is None:
        return "", ["pytesseract/Pillow not available; OCR skipped."]
    try:
        page_image = page.to_image(resolution=300).original
        return pytesseract.image_to_string(page_image), warnings
    except Exception as exc:  # pragma: no cover - runtime safety
        warnings.append(f"OCR failed on PDF page: {exc}")
        return "", warnings


def _extract_image(path: str) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    if pytesseract is None or Image is None:
        return "", ["pytesseract/Pillow not available; OCR skipped."]
    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img), warnings
    except Exception as exc:  # pragma: no cover - runtime safety
        warnings.append(f"OCR failed on image: {exc}")
        return "", warnings


def parse_invoice(text: str, custom_fields: Dict[str, str], vendor_categories: Dict[str, str]) -> Dict:
    lines = _normalize_lines(text)
    items, header_lines = _find_line_items(lines)
    items = _merge_similar_items(items)
    amounts = _extract_labeled_amounts(lines)
    item_sum = _sum_item_totals(items)
    doc_type = _detect_doc_type(lines)
    currency = _detect_currency(lines)
    tip = _detect_tip(lines)
    lowered_categories = {k.lower(): v for k, v in vendor_categories.items()}
    data = {
        "vendor": _guess_vendor(header_lines or lines),
        "date": _find_first_match(lines, DATE_PATTERNS),
        "time": _find_first_match(lines, [TIME_PATTERN]),
        "invoice_number": _find_invoice_number(lines),
        "subtotal": amounts.get("subtotal") if amounts else _find_amount(lines, labels=("subtotal",)),
        "tax": amounts.get("tax") if amounts else _find_amount(lines, labels=("tax", "vat")),
        "total": amounts.get("total") if amounts else _find_amount(lines, labels=("total", "amount due", "balance", "grand total")),
        "payment_method": _find_payment_method(lines),
        "doc_type": doc_type,
        "currency": currency,
        "tip": tip,
        "category": None,
        "items": items,
        "header_lines": header_lines,
        "warnings": [],
    }
    if not data["total"] and item_sum:
        data["total"] = round(item_sum, 2)
    if not data["subtotal"] and data["total"] and data["tax"] not in (None, ""):
        try:
            data["subtotal"] = round(float(data["total"]) - float(data["tax"]), 2)
        except Exception:
            pass
    if data["vendor"]:
        vendor_key = data["vendor"].lower()
        if vendor_key in lowered_categories:
            data["category"] = lowered_categories[vendor_key]
    if not data["total"]:
        data["warnings"].append("Total not detected.")
    if not data["items"]:
        data["warnings"].append("Line items not detected.")
    if not data["vendor"]:
        data["warnings"].append("Vendor not detected.")
    data["custom_fields"] = custom_fields
    return data


def _normalize_lines(text: str) -> List[str]:
    normalized = []
    for raw in text.splitlines():
        line = " ".join(raw.strip().split())
        if line:
            normalized.append(line)
    return normalized


def _guess_vendor(lines: List[str]) -> str:
    for line in lines[:8]:
        lower = line.lower()
        if any(x in lower for x in ("invoice", "receipt", "tax", "subtotal", "total", "amount")):
            continue
        if NUMBER_RE.search(line):
            continue
        # favor compact lines with name-like characters
        if 1 <= len(line.split()) <= 6:
            return line
    return lines[0] if lines else ""


def _detect_doc_type(lines: List[str]) -> str:
    joined = " ".join(lines).lower()
    if "invoice" in joined:
        return "invoice"
    if "receipt" in joined or "pos" in joined or "sale" in joined:
        return "receipt"
    return ""


def _detect_currency(lines: List[str]) -> str:
    joined = " ".join(lines)
    if "$" in joined:
        return "USD"
    if "€" in joined:
        return "EUR"
    if "£" in joined:
        return "GBP"
    match = re.search(r"\b(USD|EUR|GBP|CAD|AUD|CHF|JPY|CNY|INR|MXN)\b", joined, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _detect_tip(lines: List[str]) -> float:
    tip = _find_amount(lines, labels=("tip", "gratuity", "service charge"))
    return tip if tip is not None else None


def _find_first_match(lines: List[str], patterns: List[str]) -> str:
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0)
    return ""


def _find_invoice_number(lines: List[str]) -> str:
    keywords = ("invoice", "receipt", "order", "txn", "transaction", "bill")
    for line in lines:
        lower = line.lower()
        if any(k in lower for k in keywords):
            match = re.search(r"(?:no\.?|#)\s*([A-Za-z0-9\-]+)", lower)
            if match:
                return match.group(1).upper()
            match = re.search(r"(invoice|receipt|order|txn|bill)\s*[:#]?\s*([A-Za-z0-9\-]+)", line, re.IGNORECASE)
            if match:
                return match.group(2)
    return ""


def _find_amount(lines: List[str], labels: Tuple[str, ...]) -> float:
    labels_lower = tuple(label.lower() for label in labels)
    for line in reversed(lines):
        lower = line.lower()
        if any(label in lower for label in labels_lower):
            num = _last_number(line)
            if num is not None:
                return num
    return None


def _last_number(text: str) -> float:
    numbers = NUMBER_RE.findall(text)
    if not numbers:
        return None
    try:
        raw = numbers[-1].replace(",", "").replace("$", "")
        if raw.startswith("(") and raw.endswith(")"):
            raw = "-" + raw[1:-1]
        return float(raw)
    except ValueError:
        return None


def _find_payment_method(lines: List[str]) -> str:
    candidates = ("visa", "mastercard", "amex", "discover", "cash", "card", "debit", "credit", "paypal", "apple pay", "google pay")
    for line in lines:
        lower = line.lower()
        if any(c in lower for c in candidates):
            return line
    return ""


def _find_line_items(lines: List[str]) -> Tuple[List[Dict], List[str]]:
    """
    Identify line items starting at the detected table header row; everything above is returned separately.
    """
    items: List[Dict] = []
    header_keywords = ("description", "item", "product", "qty", "quantity", "hours", "rate", "unit", "price", "amount", "total", "sku")
    skip_keywords = ("total", "subtotal", "tax", "amount due", "balance")

    header_index = None
    for idx, line in enumerate(lines):
        lower = line.lower()
        hits = sum(1 for k in header_keywords if k in lower)
        if hits >= 2:
            header_index = idx
            break

    start_idx = header_index + 1 if header_index is not None else 0
    preamble = lines[:start_idx] if header_index is not None else []

    for line in lines[start_idx:]:
        lower = line.lower()
        if any(k in lower for k in skip_keywords):
            if header_index is not None:
                break
            continue
        if lower.startswith("date") or re.search(TIME_PATTERN, line, re.IGNORECASE):
            continue
        if any(re.search(pattern, line) for pattern in DATE_PATTERNS):
            continue
        candidate = _parse_item_line(line)
        if candidate:
            items.append(candidate)
    return items, preamble


def _strip_trailing_numbers(text: str) -> str:
    return re.sub(r"\s*[-+]?\d+(?:[.,]\d+)?(?:\s+[-+]?\d+(?:[.,]\d+)?){0,3}\s*$", "", text).strip()


def _extract_description(line: str) -> str:
    """
    Pull only the descriptive portion of an item line (before numeric columns), stripping generic price/fee words.
    """
    tokens = re.split(r"\s+", line.strip())
    first_num_idx = None
    for idx, tok in enumerate(tokens):
        if NUMBER_RE.search(tok):
            first_num_idx = idx
            break
    desc_tokens = tokens[:first_num_idx] if first_num_idx is not None else tokens
    drop_words = {"total", "fee", "fees", "price", "amount"}
    desc_tokens = [t for t in desc_tokens if t.lower().strip(":") not in drop_words]
    description = " ".join(desc_tokens).strip()
    if not description:
        description = _strip_trailing_numbers(line)
    return description


def _has_number(text: str) -> bool:
    return bool(NUMBER_RE.search(text))


def _parse_item_line(line: str) -> Dict:
    # Pattern like "3 x 12.99 38.97" or "2 × $10.00 $20.00"
    multi_match = re.search(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\$?\(?[-+]?\d+(?:[.,]\d+)?\)?)", line, re.IGNORECASE)
    if multi_match and NUMBER_RE.search(line):
        qty_val = _safe_float(multi_match.group(1))
        unit_val = _safe_float(multi_match.group(2))
        totals = NUMBER_RE.findall(line)
        floats = []
        for n in totals:
            try:
                floats.append(_safe_float(n))
            except ValueError:
                continue
        line_total = floats[-1] if floats else round(qty_val * unit_val, 2)
        sku_match = re.search(r"\b[A-Z0-9]{5,}\b", line)
        return {
            "description": _extract_description(line),
            "quantity": qty_val,
            "unit_price": unit_val,
            "line_total": line_total,
            "sku": sku_match.group(0) if sku_match else "",
        }

    # First try structured columns split by multiple spaces or tabs.
    columns = re.split(r"\s{2,}|\t+", line.strip())
    if len(columns) >= 3 and any(_has_number(c) for c in columns[1:]):
        desc_col = columns[0]
        numeric_cols = [c for c in columns[1:] if _has_number(c)]
        try:
            total = _safe_float(numeric_cols[-1])
            unit_price = _safe_float(numeric_cols[-2]) if len(numeric_cols) >= 2 else 0.0
            quantity = _safe_float(numeric_cols[-3]) if len(numeric_cols) >= 3 else 1.0
            if quantity == 0:
                quantity = 1.0
            sku_match = re.search(r"\b[A-Z0-9]{5,}\b", line)
            return {
                "description": desc_col.strip(),
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": total,
                "sku": sku_match.group(0) if sku_match else "",
            }
        except Exception:
            pass

    # Fallback: positional numbers.
    numbers = NUMBER_RE.findall(line)
    if len(numbers) < 2:
        return {}
    floats = []
    for n in numbers:
        try:
            floats.append(_safe_float(n))
        except ValueError:
            continue
    if len(floats) < 2:
        return {}
    total = floats[-1]
    unit_price = floats[-2] if len(floats) >= 2 else 0.0
    quantity = floats[-3] if len(floats) >= 3 else 1.0
    if quantity == 0:
        quantity = 1.0
    description = _extract_description(line)
    sku_match = re.search(r"\b[A-Z0-9]{5,}\b", line)
    return {
        "description": description,
        "quantity": quantity,
        "unit_price": unit_price,
        "line_total": total,
        "sku": sku_match.group(0) if sku_match else "",
    }


def _merge_similar_items(items: List[Dict]) -> List[Dict]:
    """
    Merge items that share the same description and (optionally) SKU/unit price.
    This reduces duplicate rows when OCR splits lines or repeats headers.
    """
    merged = {}
    for item in items or []:
        desc_key = (item.get("description") or "").strip().lower()
        sku_key = (item.get("sku") or "").strip().lower()
        try:
            unit_key = round(float(item.get("unit_price") or 0), 4)
        except Exception:
            unit_key = item.get("unit_price") or ""
        key = (desc_key, sku_key, unit_key)
        if key not in merged:
            merged[key] = dict(item)
            continue
        existing = merged[key]
        try:
            existing["quantity"] = round(float(existing.get("quantity") or 0) + float(item.get("quantity") or 0), 4)
        except Exception:
            pass
        try:
            existing["line_total"] = round(float(existing.get("line_total") or 0) + float(item.get("line_total") or 0), 2)
        except Exception:
            pass
    return list(merged.values())


def _safe_float(val: str) -> float:
    cleaned = val.replace(",", "").replace("$", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    return float(cleaned)


def _sum_item_totals(items: List[Dict]) -> float:
    total = 0.0
    count = 0
    for item in items or []:
        try:
            total += float(item.get("line_total") or 0)
            count += 1
        except (TypeError, ValueError):
            continue
    return total if count else 0.0


def _extract_labeled_amounts(lines: List[str]) -> Dict[str, float]:
    labels = {
        "subtotal": ("subtotal",),
        "tax": ("tax", "vat", "gst", "hst"),
        "total": ("total", "amount due", "balance due", "balance", "grand total"),
    }
    found: Dict[str, float] = {}
    for line in reversed(lines):
        lower = line.lower()
        for key, keys in labels.items():
            if any(k in lower for k in keys):
                num = _last_number(line)
                if num is not None and key not in found:
                    found[key] = num
                break
    return found


def preview_records(records: List[Dict]) -> None:
    summary_rows = []
    for rec in records:
        summary_rows.append(
            {
                "source": rec.get("source_file", ""),
                "vendor": rec.get("vendor", ""),
                "date": rec.get("date", ""),
                "total": rec.get("total", ""),
                "tax": rec.get("tax", ""),
                "payment": rec.get("payment_method", ""),
                "invoice_no": rec.get("invoice_number", ""),
                "category": rec.get("category", ""),
                "warnings": "; ".join(rec.get("warnings", [])),
            }
        )
    print("\n=== Document Summary ===")
    print(tabulate(summary_rows, headers="keys", tablefmt="github"))
    for rec in records:
        print(f"\n-- Items for {rec.get('source_file', 'document')} --")
        items = rec.get("items", [])
        if not items:
            print("No line items detected.")
            continue
        print(tabulate(items, headers="keys", tablefmt="github"))


def flatten_for_export(records: List[Dict]) -> List[Dict]:
    rows: List[Dict] = []
    for rec in records:
        base = {
            "source_file": rec.get("source_file", ""),
            "doc_type": rec.get("doc_type", ""),
            "vendor": rec.get("vendor", ""),
            "date": rec.get("date", ""),
            "time": rec.get("time", ""),
            "invoice_number": rec.get("invoice_number", ""),
            "payment_method": rec.get("payment_method", ""),
            "subtotal": rec.get("subtotal", ""),
            "tax": rec.get("tax", ""),
            "tip": rec.get("tip", ""),
            "total": rec.get("total", ""),
            "category": rec.get("category", ""),
            "currency": rec.get("currency", ""),
        }
        base.update(rec.get("custom_fields", {}))
        items = rec.get("items") or [{}]
        for idx, item in enumerate(items):
            row = base.copy()
            if idx > 0:
                row["invoice_number"] = ""
            row.update(
                {
                    "item_description": item.get("description", ""),
                    "item_quantity": item.get("quantity", ""),
                    "item_unit_price": item.get("unit_price", ""),
                    "item_line_total": item.get("line_total", ""),
                    "item_sku": item.get("sku", ""),
                }
            )
            rows.append(row)
    return rows


def export_records(records: List[Dict], output_dir: str, csv_name: str, xlsx_name: str) -> Tuple[str, str]:
    rows = flatten_for_export(records)
    return export_rows(rows, output_dir, csv_name, xlsx_name)


def export_rows(rows: List[Dict], output_dir: str, csv_name: str, xlsx_name: str) -> Tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, csv_name)
    xlsx_path = os.path.join(output_dir, xlsx_name)
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)
    return csv_path, xlsx_path
