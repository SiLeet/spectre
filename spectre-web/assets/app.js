// Spectre dashboard — vanilla JS, no dependencies, works offline.
// All untrusted data (process names, paths, values) is inserted with
// textContent, never innerHTML.
"use strict";

const $ = (id) => document.getElementById(id);
const MAX_REGION_ROWS = 5000;

let processes = [];
let regions = [];
let selectedPid = null;

/** GET an API endpoint and unwrap the { ok, data | error } envelope. */
async function api(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  let res;
  try {
    res = await fetch(path + qs, { headers: { Accept: "application/json" } });
  } catch (e) {
    throw new Error("server unreachable");
  }
  let body;
  try {
    body = await res.json();
  } catch (e) {
    throw new Error("HTTP " + res.status);
  }
  if (!body.ok) throw new Error(body.error || "HTTP " + res.status);
  return body.data;
}

function setStatus(el, text, isError) {
  el.textContent = text;
  el.classList.toggle("error", Boolean(isError));
}

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text == null ? "" : String(text);
  if (cls) td.className = cls;
  return td;
}

function formatSize(n) {
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MiB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(1) + " KiB";
  return n + " B";
}

// ── Processes ────────────────────────────────────────────────────────────────

async function loadProcesses() {
  const status = $("proc-status");
  setStatus(status, "Loading…");
  try {
    processes = await api("/api/processes");
    renderProcesses();
  } catch (e) {
    setStatus(status, e.message, true);
  }
}

function renderProcesses() {
  const needle = $("proc-filter").value.trim().toLowerCase();
  const body = $("proc-body");
  body.replaceChildren();
  const shown = processes.filter(
    (p) => !needle || p.name.toLowerCase().includes(needle) || String(p.pid).includes(needle)
  );
  for (const p of shown) {
    const tr = document.createElement("tr");
    tr.append(cell(p.pid, "num"), cell(p.name));
    if (p.pid === selectedPid) tr.classList.add("selected");
    tr.addEventListener("click", () => selectProcess(p));
    body.append(tr);
  }
  setStatus($("proc-status"), shown.length + " of " + processes.length + " process(es)");
}

function selectProcess(p) {
  selectedPid = p.pid;
  for (const form of [$("read-form"), $("search-form")]) form.elements.pid.value = p.pid;
  $("region-pid").textContent = "— " + p.name + " (" + p.pid + ")";
  renderProcesses();
  loadRegions();
}

// ── Regions ──────────────────────────────────────────────────────────────────

async function loadRegions() {
  if (selectedPid == null) return;
  const status = $("region-status");
  setStatus(status, "Loading…");
  $("region-body").replaceChildren();
  try {
    regions = await api("/api/regions", { pid: selectedPid });
    renderRegions();
  } catch (e) {
    regions = [];
    setStatus(status, e.message, true);
  }
}

function renderRegions() {
  const needle = $("region-filter").value.trim().toLowerCase();
  const body = $("region-body");
  body.replaceChildren();
  const shown = regions.filter((r) => !needle || r.perms.toLowerCase().includes(needle));
  for (const r of shown.slice(0, MAX_REGION_ROWS)) {
    const tr = document.createElement("tr");
    tr.title = "Click to use " + r.start + " in the read form";
    tr.append(
      cell(r.start),
      cell(r.end),
      cell(formatSize(r.size), "num"),
      cell(r.perms),
      cell(r.path || "", "path")
    );
    tr.addEventListener("click", () => useAddress(r.start));
    body.append(tr);
  }
  let text = shown.length + " of " + regions.length + " region(s)";
  if (shown.length > MAX_REGION_ROWS) text += " — showing first " + MAX_REGION_ROWS;
  setStatus($("region-status"), text);
}

// ── Read ─────────────────────────────────────────────────────────────────────

function useAddress(addr) {
  const form = $("read-form");
  form.elements.addr.value = addr;
  form.elements.addr.focus();
}

async function submitRead(ev) {
  ev.preventDefault();
  const form = ev.target;
  const out = $("read-result");
  const params = Object.fromEntries(new FormData(form));
  if (params.type !== "string" && params.type !== "bytes") delete params.size;
  form.querySelector("button").disabled = true;
  setStatus(out, "Reading…");
  try {
    const d = await api("/api/read", params);
    setStatus(
      out,
      d.address + "  (" + d.type + ", " + d.size + " byte(s), " + d.endian + "-endian)\n" +
        "value: " + (typeof d.value === "string" ? JSON.stringify(d.value) : d.value) + "\n" +
        "hex:   " + d.hex
    );
  } catch (e) {
    setStatus(out, e.message, true);
  } finally {
    form.querySelector("button").disabled = false;
  }
}

// ── Search ───────────────────────────────────────────────────────────────────

async function submitSearch(ev) {
  ev.preventDefault();
  const form = ev.target;
  const status = $("search-status");
  const list = $("search-results");
  list.replaceChildren();
  form.querySelector("button").disabled = true;
  setStatus(status, "Searching… (this can take a while for large processes)");
  try {
    const d = await api("/api/search", Object.fromEntries(new FormData(form)));
    for (const addr of d.addresses) {
      const li = document.createElement("li");
      li.textContent = addr;
      li.title = "Click to read this address";
      li.addEventListener("click", () => {
        const rf = $("read-form");
        rf.elements.pid.value = d.pid;
        rf.elements.type.value = d.type;
        useAddress(addr);
      });
      list.append(li);
    }
    setStatus(
      status,
      d.count + " match(es) for " + d.type + " = " + d.value +
        (d.truncated ? " — limit " + d.limit + " reached, more exist" : "")
    );
  } catch (e) {
    setStatus(status, e.message, true);
  } finally {
    form.querySelector("button").disabled = false;
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  $("proc-refresh").addEventListener("click", loadProcesses);
  $("proc-filter").addEventListener("input", renderProcesses);
  $("region-filter").addEventListener("input", renderRegions);
  $("read-form").addEventListener("submit", submitRead);
  $("search-form").addEventListener("submit", submitSearch);
  try {
    const info = await api("/api/info");
    $("backend").textContent = "backend: " + info.backend + " · v" + info.version;
    $("search-form").elements.limit.title = "1 – " + info.max_search_limit;
    $("read-form").elements.size.title = "string / bytes only, 1 – " + info.max_read_size;
  } catch (e) {
    setStatus($("backend"), e.message, true);
  }
  loadProcesses();
}

init();
