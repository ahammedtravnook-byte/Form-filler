import './style.css';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

/* ------------------------------------------------------------------ *
 * Coordinate model
 * ------------------------------------------------------------------ *
 * fields_config x,y are PDF points with the origin at the TOP-LEFT and
 * y growing downward — matching how the Python engine (PyMuPDF
 * insert_text / insert_textbox) places text from the top of the page.
 * So an overlay's CSS position is simply: left = x*scale, top = y*scale.
 * ------------------------------------------------------------------ */

const TEMPLATES_BASE = '/templates';
const DEFAULT_BOX_SIZE = 8;     // CheckboxGroup / Checkbox box_size default
const DEFAULT_FONT_SIZE = 9;    // text field font_size default

const state = {
  templateId: null,
  config: null,        // working copy (edited)
  original: null,      // pristine copy for reset / dirty check
  exampleData: {},
  pdfDoc: null,
  scale: 1,
  pageViewports: [],   // index -> {width, height} at scale 1
  activeField: null,
};

// ---- DOM refs -----------------------------------------------------
const el = {
  templateSelect: document.getElementById('templateSelect'),
  status: document.getElementById('status'),
  zoom: document.getElementById('zoom'),
  zoomVal: document.getElementById('zoomVal'),
  saveBtn: document.getElementById('saveBtn'),
  viewerEmpty: document.getElementById('viewerEmpty'),
  pages: document.getElementById('pages'),
  fieldList: document.getElementById('fieldList'),
  fieldFilter: document.getElementById('fieldFilter'),
};

// ---- helpers ------------------------------------------------------
function setStatus(msg, kind = '') {
  el.status.textContent = msg;
  el.status.className = 'status' + (kind ? ' ' + kind : '');
}

function fieldType(f) {
  return f.type || 'text';
}

function isTextLike(f) {
  const t = fieldType(f);
  return t === 'text' || t === 'multiline_text' || t === 'date' || t === 'signature_text';
}

function deepClone(o) {
  return JSON.parse(JSON.stringify(o));
}

function configDirty() {
  return JSON.stringify(state.config) !== JSON.stringify(state.original);
}

// ================================================================== //
// Bootstrap
// ================================================================== //
async function init() {
  try {
    const res = await fetch(`${TEMPLATES_BASE}/manifest.json`);
    const list = await res.json();
    for (const id of list) {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = id;
      el.templateSelect.appendChild(opt);
    }
    setStatus(`${list.length} templates available`);
  } catch (err) {
    setStatus('Failed to load template manifest', 'err');
    console.error(err);
  }

  el.templateSelect.addEventListener('change', () => loadTemplate(el.templateSelect.value));
  el.zoom.addEventListener('input', onZoom);
  el.saveBtn.addEventListener('click', saveConfig);
  el.fieldFilter.addEventListener('input', renderFieldList);
}

// ================================================================== //
// Load a template
// ================================================================== //
async function loadTemplate(id) {
  if (!id) return;
  state.templateId = id;
  state.activeField = null;
  setStatus(`Loading ${id}…`);
  el.saveBtn.disabled = true;

  const base = `${TEMPLATES_BASE}/${id}`;
  try {
    const [cfg, example] = await Promise.all([
      fetch(`${base}/fields_config.json`).then((r) => r.json()),
      fetch(`${base}/example_data.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);

    state.config = cfg;
    state.original = deepClone(cfg);
    // example_data may be {data:{...}} or flat {...}
    state.exampleData = example ? (example.data || example) : {};

    const pdfBytes = await fetch(`${base}/template.pdf`).then((r) => r.arrayBuffer());
    state.pdfDoc = await pdfjsLib.getDocument({ data: pdfBytes }).promise;

    await renderPages();
    renderFieldList();
    el.viewerEmpty.style.display = 'none';
    el.saveBtn.disabled = false;
    setStatus(`Loaded ${id} — ${Object.keys(cfg.fields).length} fields, ${state.pdfDoc.numPages} pages`, 'ok');
  } catch (err) {
    console.error(err);
    setStatus(`Error loading ${id}: ${err.message}`, 'err');
  }
}

// ================================================================== //
// Render PDF pages + field overlays
// ================================================================== //
async function renderPages() {
  el.pages.innerHTML = '';
  state.pageViewports = [];

  for (let p = 1; p <= state.pdfDoc.numPages; p++) {
    const page = await state.pdfDoc.getPage(p);
    const baseViewport = page.getViewport({ scale: 1 });
    state.pageViewports[p] = { width: baseViewport.width, height: baseViewport.height };

    const viewport = page.getViewport({ scale: state.scale });
    const wrap = document.createElement('div');
    wrap.className = 'page-wrap';
    wrap.dataset.page = p;
    wrap.style.width = `${viewport.width}px`;
    wrap.style.height = `${viewport.height}px`;

    const label = document.createElement('div');
    label.className = 'page-label';
    label.textContent = `Page ${p}`;
    wrap.appendChild(label);

    const canvas = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    wrap.appendChild(canvas);

    el.pages.appendChild(wrap);
    await page.render({ canvasContext: ctx, viewport }).promise;
  }
  renderOverlays();
}

// Draw / refresh the field overlays on top of every page.
function renderOverlays() {
  // remove old overlays
  el.pages.querySelectorAll('.fld, .cbx').forEach((n) => n.remove());
  const s = state.scale;

  for (const [name, f] of Object.entries(state.config.fields)) {
    const type = fieldType(f);
    if (type === 'checkbox_group') {
      for (const [optName, opt] of Object.entries(f.options || {})) {
        const box = opt.box_size || f.box_size || DEFAULT_BOX_SIZE;
        const node = makeCbx(f.page, opt.x, opt.y, box, s);
        node.dataset.field = name;
        node.dataset.opt = optName;
        node.title = `${name} › ${optName}`;
        attachPage(f.page, node);
      }
    } else if (type === 'checkbox') {
      const box = f.box_size || DEFAULT_BOX_SIZE;
      const node = makeCbx(f.page, f.x, f.y, box, s);
      node.dataset.field = name;
      node.title = name;
      attachPage(f.page, node);
    } else {
      // text-like field
      const node = document.createElement('div');
      node.className = 'fld';
      node.dataset.field = name;
      const fs = (f.font_size || DEFAULT_FONT_SIZE) * s;
      node.style.left = `${f.x * s}px`;
      node.style.top = `${f.y * s}px`;
      node.style.fontSize = `${fs}px`;
      if (f.width) node.style.minWidth = `${f.width * s}px`;
      const h = f.height ? f.height * s : fs * 1.2;
      node.style.minHeight = `${h}px`;

      const text = previewText(name, f);
      node.textContent = text;
      node.title = `${name} (x:${f.x}, y:${f.y})`;

      const anchor = document.createElement('div');
      anchor.className = 'anchor';
      node.appendChild(anchor);

      attachPage(f.page, node);
    }
  }
  highlightActive();
}

function makeCbx(pageNum, x, y, box, s) {
  const node = document.createElement('div');
  node.className = 'cbx';
  node.style.left = `${x * s}px`;
  node.style.top = `${y * s}px`;
  node.style.width = `${box * s}px`;
  node.style.height = `${box * s}px`;
  return node;
}

function attachPage(pageNum, node) {
  const wrap = el.pages.querySelector(`.page-wrap[data-page="${pageNum}"]`);
  if (wrap) wrap.appendChild(node);
}

function previewText(name, f) {
  const val = state.exampleData[f.data_key];
  if (val !== undefined && val !== null && String(val).trim() !== '') {
    return String(val);
  }
  return `«${name}»`;
}

// ================================================================== //
// Field list / editor panel
// ================================================================== //
function renderFieldList() {
  if (!state.config) return;
  const filter = el.fieldFilter.value.trim().toLowerCase();
  el.fieldList.innerHTML = '';

  for (const [name, f] of Object.entries(state.config.fields)) {
    if (filter && !name.toLowerCase().includes(filter) &&
        !(f.description || '').toLowerCase().includes(filter)) {
      continue;
    }
    el.fieldList.appendChild(buildFieldCard(name, f));
  }
}

function buildFieldCard(name, f) {
  const orig = state.original.fields[name];
  const dirty = JSON.stringify(f) !== JSON.stringify(orig);
  const type = fieldType(f);

  const card = document.createElement('div');
  card.className = 'field-card';
  card.dataset.field = name;
  if (name === state.activeField) card.classList.add('active');
  if (dirty) card.classList.add('dirty');

  // header
  const head = document.createElement('div');
  head.className = 'fc-head';
  head.innerHTML =
    `<span class="fc-name">${name}</span>` +
    `<span class="fc-type">${type} · p${f.page}</span>`;
  head.addEventListener('click', () => selectField(name));
  card.appendChild(head);

  if (f.description) {
    const d = document.createElement('div');
    d.className = 'fc-desc';
    d.textContent = f.description;
    card.appendChild(d);
  }

  if (type === 'checkbox_group') {
    for (const [optName, opt] of Object.entries(f.options || {})) {
      const block = document.createElement('div');
      block.className = 'opt-block';
      const lbl = document.createElement('div');
      lbl.className = 'opt-name';
      lbl.textContent = optName;
      block.appendChild(lbl);
      block.appendChild(coordRow(name, opt, ['x', 'y'], optName));
      card.appendChild(block);
    }
  } else {
    // text-like or single checkbox: x, y editable
    card.appendChild(coordRow(name, f, ['x', 'y'], null));
  }

  if (dirty) {
    const reset = document.createElement('button');
    reset.className = 'fc-reset';
    reset.textContent = 'reset this field';
    reset.addEventListener('click', () => resetField(name));
    card.appendChild(reset);
  }

  return card;
}

/**
 * A row of number inputs + nudge buttons that mutate `target[key]` live.
 * `optName` is non-null when the target is a checkbox-group option.
 */
function coordRow(fieldName, target, keys, optName) {
  const row = document.createElement('div');
  row.className = 'coord-row';

  for (const key of keys) {
    const label = document.createElement('label');
    label.textContent = key;
    row.appendChild(label);

    const input = document.createElement('input');
    input.type = 'number';
    input.step = '0.5';
    input.value = target[key];
    input.addEventListener('input', () => {
      const v = parseFloat(input.value);
      if (!Number.isNaN(v)) {
        target[key] = v;
        afterEdit(fieldName);
      }
    });
    row.appendChild(input);

    // nudge buttons (−/+ by 1)
    const nudge = document.createElement('div');
    nudge.className = 'nudge';
    for (const [txt, delta] of [['−', -1], ['+', 1]]) {
      const b = document.createElement('button');
      b.textContent = txt;
      b.addEventListener('click', () => {
        target[key] = Math.round((Number(target[key]) + delta) * 100) / 100;
        input.value = target[key];
        afterEdit(fieldName);
      });
      nudge.appendChild(b);
    }
    row.appendChild(nudge);
  }
  return row;
}

// After any coordinate change: re-draw overlays, refresh dirty state.
let editTimer = null;
function afterEdit(fieldName) {
  state.activeField = fieldName;
  renderOverlays();
  // debounce list rebuild so typing stays smooth
  clearTimeout(editTimer);
  editTimer = setTimeout(() => {
    refreshDirtyMarkers();
    setStatus(configDirty() ? 'Unsaved changes' : 'No changes', configDirty() ? 'warn' : '');
  }, 150);
}

function refreshDirtyMarkers() {
  el.fieldList.querySelectorAll('.field-card').forEach((card) => {
    const name = card.dataset.field;
    const dirty = JSON.stringify(state.config.fields[name]) !==
                  JSON.stringify(state.original.fields[name]);
    card.classList.toggle('dirty', dirty);
    let reset = card.querySelector('.fc-reset');
    if (dirty && !reset) {
      reset = document.createElement('button');
      reset.className = 'fc-reset';
      reset.textContent = 'reset this field';
      reset.addEventListener('click', () => resetField(name));
      card.appendChild(reset);
    } else if (!dirty && reset) {
      reset.remove();
    }
  });
}

function resetField(name) {
  state.config.fields[name] = deepClone(state.original.fields[name]);
  renderOverlays();
  renderFieldList();
  setStatus(configDirty() ? 'Unsaved changes' : 'No changes', configDirty() ? 'warn' : '');
}

function selectField(name) {
  state.activeField = name;
  highlightActive();
  // scroll the overlay into view
  const node = el.pages.querySelector(`.fld[data-field="${name}"], .cbx[data-field="${name}"]`);
  if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function highlightActive() {
  el.pages.querySelectorAll('.fld, .cbx').forEach((n) => {
    n.classList.toggle('active', n.dataset.field === state.activeField);
  });
  el.fieldList.querySelectorAll('.field-card').forEach((c) => {
    c.classList.toggle('active', c.dataset.field === state.activeField);
  });
}

// ================================================================== //
// Zoom
// ================================================================== //
async function onZoom() {
  state.scale = parseFloat(el.zoom.value);
  el.zoomVal.textContent = `${Math.round(state.scale * 100)}%`;
  if (state.pdfDoc) await renderPages();
}

// ================================================================== //
// Save -> newtemplate/<id>/newfields.json
// ================================================================== //
async function saveConfig() {
  if (!state.config || !state.templateId) return;
  el.saveBtn.disabled = true;
  setStatus('Saving…');
  try {
    const res = await fetch('/api/save-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: state.templateId, config: state.config }),
    });
    const out = await res.json();
    if (!res.ok || !out.ok) throw new Error(out.error || 'Save failed');
    // accepted config becomes the new baseline
    state.original = deepClone(state.config);
    refreshDirtyMarkers();
    setStatus(`Saved → ${out.path}`, 'ok');
  } catch (err) {
    console.error(err);
    setStatus(`Save failed: ${err.message}`, 'err');
  } finally {
    el.saveBtn.disabled = false;
  }
}

init();
