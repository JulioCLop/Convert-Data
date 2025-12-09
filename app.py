import argparse
import sys

import parser as invoice_parser


def _parse_kv_pairs(pairs):
    result = {}
    for pair in pairs or []:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract invoice/receipt data and export CSV/XLSX.")
    parser.add_argument("files", nargs="+", help="Files to process (PDF, image, or text).")
    parser.add_argument("--output-dir", default="output", help="Directory to write CSV/XLSX.")
    parser.add_argument("--csv-name", default="invoices.csv", help="CSV file name.")
    parser.add_argument("--xlsx-name", default="invoices.xlsx", help="Excel file name.")
    parser.add_argument("--custom-field", action="append", help="Custom field key=value (repeatable).")
    parser.add_argument("--category", action="append", help="Vendor-to-category mapping Vendor=Category (repeatable).")
    parser.add_argument("--force-ocr", action="store_true", help="Force OCR for PDFs (otherwise text extraction is used).")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per PDF to process.")
    parser.add_argument("--no-export", action="store_true", help="Only show preview, skip writing files.")
    args = parser.parse_args()

    custom_fields = _parse_kv_pairs(args.custom_field)
    vendor_categories = _parse_kv_pairs(args.category)

    records = []
    for path in args.files:
        text, warnings = invoice_parser.extract_text(path, force_ocr=args.force_ocr, max_pages=args.max_pages)
        if not text.strip():
            warnings.append("No text detected; check OCR or source file.")
        parsed = invoice_parser.parse_invoice(text, custom_fields=custom_fields, vendor_categories=vendor_categories)
        parsed["source_file"] = path
        parsed["warnings"] = warnings + parsed.get("warnings", [])
        records.append(parsed)

    invoice_parser.preview_records(records)

    if args.no_export:
        return
    csv_path, xlsx_path = invoice_parser.export_records(records, args.output_dir, args.csv_name, args.xlsx_name)
    print(f"\nWrote CSV: {csv_path}")
    print(f"Wrote XLSX: {xlsx_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
