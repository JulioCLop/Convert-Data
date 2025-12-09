Invoice to CSV/XLSX Extractor
==============================

Command-line utility to ingest receipts/invoices (PDF, image, or text), extract structured fields, preview them, and export combined CSV and Excel files. Supports custom fields and category mapping for budgeting/expense reporting.

Quick start
-----------

1. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
2. Run extraction on one or more files:
   ```bash
   python3 app.py samples/sample_invoice.txt \
     --output-dir output \
     --custom-field Project="Q4 Launch" \
     --category Starbucks=Meals Uber=Travel
   ```
3. Outputs:
   - Preview tables printed to console
   - Aggregated CSV and XLSX in `output/`

Web UI
------

1. Start the server (set `PORT` if 5000 is already in use, e.g., by macOS AirPlay):
   ```bash
   python3 server.py
   # or
   PORT=5050 python3 server.py
   ```
   Then open http://localhost:<PORT>
2. Drag-and-drop PDFs/images/text, add custom fields and vendor→category rules, choose OCR/max pages, then click **Run extraction**.
3. Preview parsed vendor/date/totals/items, see warnings, and download aggregated CSV/XLSX directly from the UI.
4. Already have structured data? Upload a CSV/XLS/XLSX and the UI will preview its rows and merge them into the downloads.
5. The UI now prefers the same origin/port you loaded it from. If you serve the UI from another host/port (e.g., Live Server) or via `file://`, set the API base once via `?api_base=http://127.0.0.1:5000` in the URL (persists locally) or run `window.__API_BASE = "http://127.0.0.1:5000"` in the console to point at the Flask server.

Tip: If you serve the static files from another port (e.g., VS Code Live Server), append `?api_base=http://localhost:5000` to the URL (persists) or set `window.__API_BASE = "http://localhost:5000"` so the front end can reach the Flask API with CORS enabled.

Features
--------

- PDF text extraction (`pdfplumber`), image OCR (`pytesseract` + `Pillow`), or raw text files.
- Heuristic parsing for vendor, date, invoice/receipt number, totals, taxes, payment method, and line items (qty, unit, total, SKU when present).
- Multiple documents aggregated into one dataset.
- Custom fields per run (e.g., `Project`, `Department`, `CostCenter`, `Notes`).
- Optional vendor-to-category mapping for expense reporting.
- Exports clean, normalized CSV and Excel.
- Flags uncertain or missing fields in the preview so you can correct upstream.

CLI usage
---------

```bash
python3 app.py <files...> [options]

Options:
  --output-dir PATH          Where to write CSV/XLSX (default: output)
  --csv-name NAME            CSV filename (default: invoices.csv)
  --xlsx-name NAME           XLSX filename (default: invoices.xlsx)
  --custom-field K=V         Add custom fields (repeatable)
  --category Vendor=Name     Map vendor to category (repeatable)
  --force-ocr                Force OCR even for PDFs (otherwise text extraction is used)
  --max-pages N              Limit pages processed per PDF (default: 5)
  --no-export                Skip writing files; just show preview
```

Notes and limitations
---------------------

- OCR requires a local Tesseract binary. If absent, image processing will skip with a warning; PDFs will still be processed via text extraction.
- Parsing is heuristic; always review the preview for ambiguous fields.
- Line-item detection expects each item on its own line with quantities/prices; highly stylized layouts may need manual adjustments.

Project layout
--------------

- `app.py` — main CLI orchestrating ingest, parsing, and export.
- `parser.py` — extraction and normalization logic.
- `requirements.txt` — dependencies.
- `samples/` — example text invoice for quick testing.

Extending
---------

- Plug in your own categorization rules or GL/account mapping in `parser.py`.
- Add vendor-specific parsers in `parser.py` by keying off vendor names/keywords.
- Integrate with QuickBooks/Xero/Shopify by consuming the CSV/XLSX outputs.

Troubleshooting
---------------

- Missing Tesseract: install via `brew install tesseract` (macOS) or your package manager.
- Bad OCR: try `--force-ocr` on PDFs with embedded images.
- Too many pages: use `--max-pages 1` for single-receipt PDFs.
- Port 5000 busy (common with macOS AirPlay): either disable AirPlay Receiver or start the server with a different port, e.g., `PORT=5050 python3 server.py`, and open that port in the browser.
