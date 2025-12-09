const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const browseBtn = document.getElementById("browseBtn");
const fileList = document.getElementById("fileList");
const processBtn = document.getElementById("processBtn");
const statusEl = document.getElementById("status");
const csvLink = document.getElementById("csvLink");
const xlsxLink = document.getElementById("xlsxLink");
const summaryEl = document.getElementById("summary");
const itemsTable = document.getElementById("itemsTable");
const rowsTable = document.getElementById("rowsTable");
const warningsEl = document.getElementById("warnings");
const recordSelect = document.getElementById("recordSelect");
let API_BASE = resolveApiBase();

let files = [];
let records = [];
let rows = [];

function setStatus(text, tone = "info") {
  statusEl.textContent = text;
  statusEl.dataset.tone = tone;
}

function renderFileList() {
  if (!files.length) {
    fileList.innerHTML = `<div class="muted small">No files yet.</div>`;
    return;
  }
  fileList.innerHTML = files
    .map((f) => `<span class="file-chip">${f.name}</span>`)
    .join("");
}

function addCustomFieldRow(key = "", value = "") {
  const container = document.getElementById("customFields");
  const row = document.createElement("div");
  row.className = "field-row";
  row.innerHTML = `
    <input type="text" placeholder="Key (e.g., Project)" value="${key}" class="custom-key" />
    <input type="text" placeholder="Value (e.g., Alpha)" value="${value}" class="custom-value" />
    <button class="btn btn-ghost" type="button">×</button>
  `;
  row.querySelector("button").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function addCategoryRow(vendor = "", category = "") {
  const container = document.getElementById("categoryFields");
  const row = document.createElement("div");
  row.className = "field-row";
  row.innerHTML = `
    <input type="text" placeholder="Vendor (e.g., Uber)" value="${vendor}" class="category-vendor" />
    <input type="text" placeholder="Category (e.g., Travel)" value="${category}" class="category-name" />
    <button class="btn btn-ghost" type="button">×</button>
  `;
  row.querySelector("button").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function collectCustomFields() {
  const pairs = {};
  document.querySelectorAll(".custom-key").forEach((el, idx) => {
    const key = el.value.trim();
    const val = document.querySelectorAll(".custom-value")[idx].value.trim();
    if (key) pairs[key] = val;
  });
  return pairs;
}

function collectCategories() {
  const pairs = {};
  document.querySelectorAll(".category-vendor").forEach((el, idx) => {
    const key = el.value.trim();
    const val = document.querySelectorAll(".category-name")[idx].value.trim();
    if (key) pairs[key] = val;
  });
  return pairs;
}

function toggleDownloads(csvUrl, xlsxUrl) {
  if (csvUrl) {
    csvLink.href = withBase(csvUrl);
    csvLink.setAttribute("aria-disabled", "false");
  } else {
    csvLink.href = "#";
    csvLink.setAttribute("aria-disabled", "true");
  }
  if (xlsxUrl) {
    xlsxLink.href = withBase(xlsxUrl);
    xlsxLink.setAttribute("aria-disabled", "false");
  } else {
    xlsxLink.href = "#";
    xlsxLink.setAttribute("aria-disabled", "true");
  }
}

function handleFiles(selected) {
  files = [...files, ...selected];
  renderFileList();
}

async function processDocuments() {
  if (!files.length) {
    setStatus("Add at least one file.", "warn");
    return;
  }
  processBtn.disabled = true;
  setStatus("Processing…", "info");
  toggleDownloads(null, null);

  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("forceOcr", document.getElementById("forceOcr").checked);
  form.append("maxPages", document.getElementById("maxPages").value || "5");
  form.append("customFields", JSON.stringify(collectCustomFields()));
  form.append("categories", JSON.stringify(collectCategories()));

  try {
    const res = await fetch(withBase("/api/process"), {
      method: "POST",
      body: form,
      mode: isSameOrigin() ? "same-origin" : "cors",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to process files.");
    }
    const data = await res.json();
    records = data.records || [];
    rows = data.rows || [];
    renderSummary(records);
    populateRecordSelect(records);
    renderItems();
    renderRows(rows);
    renderWarnings(data.warnings || []);
    toggleDownloads(data.csv_url, data.xlsx_url);
    setStatus("Ready — review preview, then download.", "success");
  } catch (err) {
    console.error(err);
    const hint = API_BASE ? `Check that the API is running at ${API_BASE}.` : "Check that the server is running.";
    setStatus(`${err.message || "Failed to fetch"} — ${hint}`, "error");
  } finally {
    processBtn.disabled = false;
  }
}

function withBase(path) {
  return buildUrl(API_BASE, path);
}

function isSameOrigin(base = API_BASE) {
  try {
    const baseUrl = new URL(base || "", window.location.href);
    return baseUrl.origin === window.location.origin;
  } catch (_e) {
    return true;
  }
}

function resolveApiBase() {
  const queryBase = readApiBaseFromQuery();
  if (queryBase) {
    persistApiBase(queryBase);
    return queryBase;
  }
  if (window.__API_BASE) return window.__API_BASE;
  const stored = readApiBaseFromStorage();
  if (stored) return stored;
  const origin = window.location.origin || "";
  const isFile = origin.startsWith("file://");
  const host = window.location.hostname || "127.0.0.1";
  const proto = window.location.protocol || "http:";
  const defaultBase = `${proto}//${host}:5000`;
  // Prefer same-origin when served over HTTP(S) so custom ports (e.g., PORT=5050) just work.
  if (window.location.port) return origin;
  if (!origin || isFile) return defaultBase;
  if (/^(localhost|127\.0\.0\.1)$/i.test(host)) return defaultBase;
  return origin;
}

function buildUrl(base, path) {
  const cleanBase = (base || "").replace(/\/$/, "");
  return `${cleanBase}${path}`;
}

function readApiBaseFromQuery() {
  try {
    const params = new URLSearchParams(window.location.search);
    return (params.get("api_base") || params.get("api") || "").trim();
  } catch (_e) {
    return "";
  }
}

function readApiBaseFromStorage() {
  try {
    return localStorage.getItem("apiBase") || "";
  } catch (_e) {
    return "";
  }
}

function persistApiBase(base) {
  try {
    if (base) localStorage.setItem("apiBase", base);
  } catch (_e) {}
}

function setApiBase(base) {
  if (!base) return;
  API_BASE = base;
  persistApiBase(base);
}

function fallbackApiBases() {
  const host = window.location.hostname || "127.0.0.1";
  const proto = window.location.protocol === "https:" ? "https:" : "http:";
  const defaults = [`${proto}//${host}:5050`, `${proto}//${host}:5000`];
  return defaults;
}

function uniqueList(list) {
  return Array.from(new Set(list.filter(Boolean)));
}

function deriveRowColumns(rowsData) {
  const baseOrder = [
    "source_file",
    "vendor",
    "category",
    "date",
    "time",
    "invoice_number",
    "payment_method",
    "subtotal",
    "tax",
    "total",
  ];
  const itemOrder = ["item_description", "item_quantity", "item_unit_price", "item_line_total", "item_sku"];
  const seen = new Set();
  rowsData.forEach((row) => Object.keys(row || {}).forEach((k) => seen.add(k)));
  const custom = Array.from(seen).filter((k) => !baseOrder.includes(k) && !itemOrder.includes(k)).sort();
  return [...baseOrder.filter((k) => seen.has(k)), ...custom, ...itemOrder.filter((k) => seen.has(k))];
}

function renderSummary(docs) {
  if (!docs.length) {
    summaryEl.innerHTML = `<div class="muted small">No preview yet. Upload files and run extraction.</div>`;
    return;
  }
  const cards = docs
    .map(
      (doc, idx) => `
      <div class="card">
        <div class="label">Document ${idx + 1}</div>
        <div class="value"><strong>${escapeHtml(doc.vendor || "Unknown vendor")}</strong></div>
        <div class="small">${escapeHtml(doc.source_file || "")}</div>
        <div class="grid-2" style="margin-top: 8px;">
          <div class="small">Date</div><div>${escapeHtml(doc.date || "—")}</div>
          <div class="small">Invoice #</div><div>${escapeHtml(doc.invoice_number || "—")}</div>
          <div class="small">Payment</div><div>${escapeHtml(doc.payment_method || "—")}</div>
          <div class="small">Category</div><div>${escapeHtml(doc.category || "—")}</div>
          <div class="small">Total</div><div>${formatNumber(doc.total)}</div>
          <div class="small">Tax</div><div>${formatNumber(doc.tax)}</div>
        </div>
      </div>
    `
    )
    .join("");
  summaryEl.innerHTML = `<div class="summary-grid">${cards}</div>`;
}

function populateRecordSelect(docs) {
  recordSelect.innerHTML = "";
  if (!docs.length) {
    recordSelect.disabled = true;
    return;
  }
  docs.forEach((doc, idx) => {
    const option = document.createElement("option");
    option.value = idx;
    option.textContent = `Doc ${idx + 1}: ${doc.vendor || doc.source_file || "Untitled"}`;
    recordSelect.appendChild(option);
  });
  recordSelect.disabled = false;
}

function renderItems() {
  if (!records.length) {
    itemsTable.innerHTML = `<div class="muted small">No line items yet.</div>`;
    return;
  }
  const idx = Number(recordSelect.value || 0);
  const doc = records[idx] || records[0];
  const items = doc.items || [];
  if (!items.length) {
    itemsTable.innerHTML = `<div class="muted small">No items detected for this document.</div>`;
    return;
  }
  const keys = Object.keys(items[0] || {});
  const preferred = ["description", "quantity", "unit_price", "line_total", "sku"];
  const usePreferred = preferred.every((k) => Object.prototype.hasOwnProperty.call(items[0], k));
  const cols = usePreferred ? preferred : keys;
  itemsTable.innerHTML = renderTable(items, cols);
}

function renderRows(dataRows) {
  if (!dataRows.length) {
    rowsTable.innerHTML = `<div class="muted small">No export rows yet.</div>`;
    return;
  }
  const cols = deriveRowColumns(dataRows);
  rowsTable.innerHTML = renderTable(dataRows, cols);
}

function renderWarnings(warns) {
  if (!warns.length) {
    warningsEl.innerHTML = `<span class="pill" style="border-color: rgba(52, 211, 153, 0.5); background: rgba(52, 211, 153, 0.14); color: var(--success);">All clear</span>`;
    return;
  }
  warningsEl.innerHTML = warns.map((w) => `<span class="pill">${escapeHtml(w)}</span>`).join("");
}

function renderTable(data, keys) {
  const header = keys
    .map((k) => `<th>${escapeHtml(k.replace(/_/g, " "))}</th>`)
    .join("");
  const body = data
    .map((row) => {
      return `<tr>${keys
        .map((k) => `<td>${escapeHtml(formatMaybeNumber(row[k]))}</td>`)
        .join("")}</tr>`;
    })
    .join("");
  return `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function formatMaybeNumber(val) {
  if (typeof val === "number") return formatNumber(val);
  if (val === null || val === undefined) return "";
  return String(val);
}

function formatNumber(val) {
  if (val === null || val === undefined || val === "") return "—";
  const num = Number(val);
  if (Number.isNaN(num)) return val;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Event wiring
dropzone.addEventListener("click", () => fileInput.click());
browseBtn.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("is-drag");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-drag"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("is-drag");
  handleFiles(Array.from(e.dataTransfer.files));
});

fileInput.addEventListener("change", (e) => {
  handleFiles(Array.from(e.target.files));
});

processBtn.addEventListener("click", processDocuments);
recordSelect.addEventListener("change", renderItems);

// Seed with one blank row each
addCustomFieldRow("Project", "Q4 Launch");
addCategoryRow("Starbucks", "Meals");

async function pingApi() {
  const candidates = uniqueList([API_BASE, ...fallbackApiBases()]);
  const tried = [];
  for (const base of candidates) {
    const url = buildUrl(base || window.location.origin, "/api/health");
    tried.push(base || "current origin");
    try {
      const res = await fetch(url, { method: "GET", mode: isSameOrigin(base) ? "same-origin" : "cors" });
      if (res.ok) {
        if (base && base !== API_BASE) setApiBase(base);
        setStatus(`API reachable at ${base || "current origin"}`, "success");
        return;
      }
    } catch (_e) {
      // try next candidate
    }
  }
  setStatus(
    `Failed to reach API. Tried: ${tried.join(", ")}. Start the server or set ?api_base=/window.__API_BASE.`,
    "error"
  );
}

renderFileList();
setStatus(`Ready — API: ${API_BASE || "relative origin"}`, "info");
recordSelect.disabled = true;
pingApi();
