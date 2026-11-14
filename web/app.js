// Static MapLibre viewer. Reads files in web/data/ (see ../CONTRACTS.md). Every missing file shows "data not loaded yet".
// Serve over http (cd web && python -m http.server 8000); opening index.html as a file:// URL cannot fetch data.

const CONFIG = {
  center: [0, 0], // TODO: [lon, lat] of the AOI (CLAUDE.md "Confirmed facts")
  zoom: 2,        // TODO: zoom for the AOI
  dataDir: 'data',
  changeRangeDb: 6, // change layers are coloured over -6..+6 dB
};

const NOT_LOADED = 'data not loaded yet';
const COLORS = { early: '#f59e0b', late: '#be123c', ref: '#2563eb' };
const $ = (id) => document.getElementById(id);
const dataUrl = (name) => new URL(`${CONFIG.dataDir}/${name}`, document.baseURI).href;

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text; // textContent only: data files are never parsed as HTML
  if (cls) n.className = cls;
  return n;
}

// ---------- data loading ----------

// Returns {data} or {error: 'missing' | 'invalid'}.
async function getJSON(name) {
  let r;
  try { r = await fetch(dataUrl(name)); } catch { return { error: 'missing' }; }
  if (!r.ok) return { error: 'missing' };
  try { return { data: await r.json() }; } catch { return { error: 'invalid' }; }
}

const failMsg = (name, res) => (res.error === 'invalid' ? `${name} could not be read` : NOT_LOADED);

async function exists(url) {
  try { return (await fetch(url, { method: 'HEAD' })).ok; } catch { return false; }
}

// ---------- map ----------

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty', // OpenFreeMap, no API key
  center: CONFIG.center,
  zoom: CONFIG.zoom,
});
if (CONFIG.center[0] === 0 && CONFIG.center[1] === 0) $('aoi-note').hidden = false;
$('ramp-min').textContent = `-${CONFIG.changeRangeDb} dB`;
$('ramp-max').textContent = `+${CONFIG.changeRangeDb} dB`;
maplibregl.addProtocol('cog', MaplibreCOGProtocol.cogProtocol);

const state = { dates: [], date: null, cogToken: { hh: 0, hv: 0 } };

function setVisible(id, on) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

map.on('load', async () => {
  const [det, ref, metrics, summary] = await Promise.all([
    getJSON('detections.geojson'),
    getJSON('reference_alerts.geojson'),
    getJSON('metrics.json'),
    getJSON('summary.json'),
  ]);

  // Reference first so detections draw on top of it.
  if (ref.data) {
    map.addSource('ref', { type: 'geojson', data: ref.data });
    map.addLayer({
      id: 'ref', type: 'fill', source: 'ref',
      paint: { 'fill-color': COLORS.ref, 'fill-opacity': 0.25, 'fill-outline-color': COLORS.ref },
      layout: { visibility: $('t-ref').checked ? 'visible' : 'none' },
    });
  } else $('s-ref').textContent = failMsg('reference_alerts.geojson', ref);

  if (det.data) {
    map.addSource('det', { type: 'geojson', data: det.data });
    map.addLayer({
      id: 'det', type: 'fill', source: 'det',
      paint: {
        'fill-color': ['match', ['get', 'stage'], 'early', COLORS.early, 'late', COLORS.late, '#6b7280'],
        'fill-opacity': 0.6,
        'fill-outline-color': '#111827',
      },
      layout: { visibility: $('t-det').checked ? 'visible' : 'none' },
    });
  } else $('s-det').textContent = failMsg('detections.geojson', det);

  renderAccuracy(metrics);
  renderSummary(summary);

  const dates = new Set();
  det.data?.features?.forEach((f) => f.properties?.date && dates.add(f.properties.date));
  if (Array.isArray(metrics.data?.dates)) metrics.data.dates.forEach((d) => dates.add(d));
  if (Array.isArray(summary.data?.by_date)) summary.data.by_date.forEach((r) => r?.date && dates.add(r.date));
  setupDates([...dates].sort());
});

$('t-det').onchange = (e) => setVisible('det', e.target.checked);
$('t-ref').onchange = (e) => setVisible('ref', e.target.checked);
$('t-hh').onchange = () => updateCog('hh');
$('t-hv').onchange = () => updateCog('hv');

// ---------- date slider ----------

function setupDates(dates) {
  state.dates = dates;
  const s = $('date-slider');
  if (!dates.length) return; // label keeps saying "data not loaded yet"
  s.min = 0; s.max = dates.length - 1; s.value = dates.length - 1; s.disabled = false;
  $('date-label').classList.remove('missing');
  s.oninput = applyDate;
  applyDate();
}

function applyDate() {
  state.date = state.dates[$('date-slider').value];
  $('date-label').textContent = state.date;
  if (map.getLayer('det')) map.setFilter('det', ['<=', ['get', 'date'], state.date]); // ISO dates sort as strings
  updateCog('hh');
  updateCog('hv');
}

// ---------- change COGs (cog:// protocol, no build step) ----------

// Blue = drop, grey = no change (transparent), red = rise. Called for every pixel, so keep it cheap.
function changeColor(pixel, color) {
  const v = pixel[0];
  if (!Number.isFinite(v)) { color.set([0, 0, 0, 0]); return; }
  const t = Math.max(-1, Math.min(1, v / CONFIG.changeRangeDb));
  const a = Math.min(1, Math.abs(t) * 2) * 200; // small changes fade out
  color.set(t < 0 ? [37, 99, 235, a] : [220, 38, 38, a]);
}

async function updateCog(kind) {
  const id = `cog-${kind}`;
  const token = ++state.cogToken[kind];
  if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(id)) map.removeSource(id);
  const status = $(`s-${kind}`);
  status.textContent = '';
  if (!$(`t-${kind}`).checked) return;
  if (!state.date) { status.textContent = NOT_LOADED; return; }

  const url = dataUrl(`change_${kind}_${state.date}.tif`); // absolute: the protocol fetches it directly
  const ok = await exists(url);
  if (token !== state.cogToken[kind]) return; // superseded by a newer slider move or toggle
  if (!ok) { status.textContent = NOT_LOADED; return; }

  MaplibreCOGProtocol.setColorFunction(url, changeColor);
  map.addSource(id, { type: 'raster', url: `cog://${url}`, tileSize: 256 });
  const before = ['ref', 'det'].find((l) => map.getLayer(l));
  map.addLayer({ id, type: 'raster', source: id }, before);
}

// ---------- panels ----------

const pct = (v) => (Number.isFinite(v) ? v.toFixed(2) : '?');
const num = (v) => (Number.isFinite(v) ? String(v) : '?');
const ha = (v) => (Number.isFinite(v) ? `${v.toFixed(1)} ha` : '?');

function kvList(rows) {
  const dl = el('dl', undefined, 'kv');
  rows.forEach(([k, v]) => { dl.append(el('dt', k), el('dd', v)); });
  return dl;
}

// Expects metrics.json: {agreement: {precision, recall, f1, ...} | null, hand_labeled: {precision, n_sample, n_unsure} | null,
// reference_source, notes}. See web/README.md ("Assumed file shapes").
function renderAccuracy(res) {
  const box = $('metrics');
  box.replaceChildren();
  box.classList.remove('missing');
  if (!res.data) { box.classList.add('missing'); box.textContent = failMsg('metrics.json', res); return; }
  const m = res.data;
  box.append(el('p', 'Agreement with RADD/GLAD alerts, a reference, not ground truth.', 'caption'));

  const a = m.agreement;
  if (a && typeof a === 'object') {
    box.append(kvList([
      ['Agreement (holdout) precision', pct(a.precision)],
      ['Agreement (holdout) recall', pct(a.recall)],
      ['Agreement (holdout) F1', pct(a.f1)],
      ...(a.n_detections !== undefined ? [['Detections', num(a.n_detections)]] : []),
      ...(a.n_reference !== undefined ? [['Reference alerts', num(a.n_reference)]] : []),
    ]));
  } else box.append(el('p', 'agreement (holdout) not available yet', 'missing'));

  const h = m.hand_labeled;
  box.append(el('h3', 'Hand-labeled sample', 'hint'));
  if (h && typeof h === 'object') {
    box.append(kvList([
      ['Precision', pct(h.precision)],
      ['n_sample', num(h.n_sample)],
      ['n_unsure', num(h.n_unsure)],
    ]));
  } else box.append(el('p', 'hand-labeled sample pending', 'missing'));

  if (m.reference_source) box.append(el('p', `Reference: ${m.reference_source}`, 'hint'));
  if (m.notes) box.append(el('p', m.notes, 'hint'));
}

// Expects summary.json: {n_detections, total_ha, early_ha, late_ha (any subset), by_date: [{date, early_ha, late_ha}],
// tuning_split: {...}}. See web/README.md ("Assumed file shapes").
function renderSummary(res) {
  const box = $('summary');
  box.replaceChildren();
  box.classList.remove('missing');
  if (!res.data) { box.classList.add('missing'); box.textContent = failMsg('summary.json', res); return; }
  const s = res.data;

  const totals = [
    ['Detections', s.n_detections, num],
    ['Total area', s.total_ha, ha],
    ['Early stage', s.early_ha, ha],
    ['Late stage', s.late_ha, ha],
  ].filter(([, v]) => v !== undefined).map(([k, v, f]) => [k, f(v)]);
  if (totals.length) box.append(kvList(totals));

  if (Array.isArray(s.by_date) && s.by_date.length) box.append(barChart(s.by_date));
  else box.append(el('p', 'no by-date breakdown in summary.json', 'missing'));

  if (s.tuning_split && typeof s.tuning_split === 'object') {
    box.append(el('h3', 'Tuning split', 'hint'));
    box.append(kvList(flatten(s.tuning_split)));
  }
}

function flatten(obj, prefix = '') {
  return Object.entries(obj).flatMap(([k, v]) => {
    const key = prefix ? `${prefix} ${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) return flatten(v, key);
    return [[key.replace(/_/g, ' '), Array.isArray(v) ? v.join(', ') : String(v)]];
  });
}

// One stacked bar per date: early vs late hectares.
function barChart(rows) {
  const clean = rows
    .map((r) => ({ date: String(r.date), early: Number(r.early_ha) || 0, late: Number(r.late_ha) || 0 }))
    .sort((x, y) => x.date.localeCompare(y.date));
  const max = Math.max(...clean.map((r) => r.early + r.late), 1e-9);
  const chart = el('div', undefined, 'chart');
  chart.setAttribute('role', 'img');
  chart.setAttribute('aria-label', 'Hectares of detected disturbance by date, early versus late stage');
  clean.forEach((r) => {
    const row = el('div', undefined, 'bar-row');
    const bar = el('div', undefined, 'bar');
    const e = el('span', undefined, 'early');
    const l = el('span', undefined, 'late');
    e.style.width = `${(r.early / max) * 100}%`;
    l.style.width = `${(r.late / max) * 100}%`;
    e.title = `early ${r.early.toFixed(1)} ha`;
    l.title = `late ${r.late.toFixed(1)} ha`;
    bar.append(e, l);
    row.append(el('span', r.date), bar, el('span', `${(r.early + r.late).toFixed(1)} ha`, 'tot'));
    chart.append(row);
  });
  const key = el('div', undefined, 'chart-key');
  [['early', 'Early (HH-led)'], ['late', 'Late (HV-led)']].forEach(([c, t]) => {
    const k = el('span');
    const sw = el('i', undefined, 'sw');
    sw.style.background = COLORS[c];
    k.append(sw, t);
    key.append(k);
  });
  chart.append(key);
  return chart;
}
