// Static MapLibre viewer. Reads files in web/data/ (see ../CONTRACTS.md). Every missing file shows "data not loaded yet".
// Serve over http (cd web && npx http-server -p 8000); opening index.html as a file:// URL cannot fetch data.
// Text from data files is only ever rendered with textContent (plain text), never as HTML.

// All AOI values below are copied from CLAUDE.md "CURRENT AOI" (S Para, switched 2026-11-14). Update CLAUDE.md first.
const CONFIG = {
  center: [-54.699, -8.1995],        // lon, lat: midpoint of the bbox below
  bbox: [-54.7900, -8.2900, -54.6080, -8.1090], // W S E N, EPSG:4326, 20 x 20 km analysis window
  fitPaddingPx: 40,                  // padding around the window for the initial view
  minZoomBelowFit: 1.5,              // minZoom = initial fitted zoom minus this
  maxBoundsPad: 1.0,                 // pan limit: window grown by this many window-widths/heights on each side
  windowKm: 20,
  aoi: {
    name: 'S Para, BR (Novo Progresso)',
    track: 2, frame: 174, direction: 'ascending',
    // The 9 dates in the stack; CLAUDE.md: all used, none excluded.
    dates: ['2026-06-26', '2026-07-08', '2026-07-20', '2026-08-13', '2026-08-25', '2026-09-06', '2026-09-18', '2026-09-30', '2026-10-12'],
    excluded: null, // or { date, reason } if CLAUDE.md lists a bad granule for this stack
  },
  dataDir: 'data',
  changeRangeDb: 6, // change layers are coloured over -6..+6 dB
};

const NOT_LOADED = 'data not loaded yet';
const COLORS = { early: '#f59e0b', late: '#be123c', ref: '#2563eb' };
const $ = (id) => document.getElementById(id);
const dataUrl = (name) => new URL(`${CONFIG.dataDir}/${name}`, document.baseURI).href;

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
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

// ---------- field checking (shapes come from CONTRACTS.md; nothing is guessed) ----------

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const CHECKS = {
  num: (v) => typeof v === 'number' && Number.isFinite(v),
  nonneg: (v) => typeof v === 'number' && Number.isFinite(v) && v >= 0,
  count: (v) => Number.isInteger(v) && v >= 0,
  unit: (v) => typeof v === 'number' && v >= 0 && v <= 1,
  str: (v) => typeof v === 'string',
  date: (v) => typeof v === 'string' && DATE_RE.test(v),
  dates: (v) => Array.isArray(v) && v.every((d) => typeof d === 'string' && DATE_RE.test(d)),
  obj: (v) => v === null || (typeof v === 'object' && !Array.isArray(v)),
  rows: (v) => Array.isArray(v),
};

// Copies the fields of `obj` that exist and have the right type; records a message for every field that is
// missing, has an unexpected type/value, or is not in the contract. Those fields are skipped.
function readFields(obj, spec, path, problems) {
  const out = {};
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    problems.push(`${path || 'file'} is not an object`);
    return out;
  }
  for (const [k, type] of Object.entries(spec)) {
    if (!(k in obj)) problems.push(`${path}${k} is missing (skipped)`);
    else if (!CHECKS[type](obj[k])) problems.push(`${path}${k} has an unexpected type or value (skipped)`);
    else out[k] = obj[k];
  }
  for (const k of Object.keys(obj)) if (!(k in spec)) problems.push(`${path}${k} is an unexpected field (ignored)`);
  return out;
}

function problemList(file, problems) {
  if (!problems.length) return null;
  const ul = el('ul', undefined, 'problems');
  problems.forEach((p) => ul.append(el('li', `${file}: ${p}`)));
  return ul;
}

// ---------- map ----------

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty', // OpenFreeMap, no API key
  center: CONFIG.center,
  zoom: 9, // replaced right below by the fit to the analysis window
});

// Initial view = the analysis window; zoom-out and panning are limited to its surroundings.
(function limitView() {
  const [w, s, e, n] = CONFIG.bbox;
  const pad = CONFIG.fitPaddingPx;
  const sidebar = window.innerWidth > 600 ? 320 : 0; // the sidebar covers the left edge of the map
  map.fitBounds(CONFIG.bbox, { padding: { top: pad, bottom: pad, right: pad, left: pad + sidebar }, animate: false });
  map.setMinZoom(map.getZoom() - CONFIG.minZoomBelowFit);
  const dw = (e - w) * CONFIG.maxBoundsPad;
  const dh = (n - s) * CONFIG.maxBoundsPad;
  map.setMaxBounds([[w - dw, s - dh], [e + dw, n + dh]]);
})();

function windowOutline() {
  const [w, s, e, n] = CONFIG.bbox;
  return {
    type: 'Feature', properties: {},
    geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, // from CONFIG, not a data file
  };
}

function addWindowOutline() {
  map.addSource('window', { type: 'geojson', data: windowOutline() });
  map.addLayer({ id: 'window', type: 'line', source: 'window', paint: { 'line-color': '#111827', 'line-width': 1.5, 'line-dasharray': [3, 2] } });
  const label = el('div', 'Analysis window', 'window-label');
  new maplibregl.Marker({ element: label, anchor: 'bottom-left' }).setLngLat([CONFIG.bbox[0], CONFIG.bbox[3]]).addTo(map);
}

function renderAoi() {
  const a = CONFIG.aoi;
  const box = $('aoi');
  box.replaceChildren(
    el('p', `Area: ${a.name}. NISAR track ${a.track}, frame ${a.frame}, ${a.direction}.`),
    el('p', `NISAR passes in the stack (${a.dates.length}): ${a.dates.join(', ')}.`),
    el('p', a.excluded ? `${a.excluded.date} is excluded: ${a.excluded.reason}.` : `All ${a.dates.length} dates are used; none is excluded.`),
  );
  const d = a.dates;
  $('tested').textContent =
    `What was tested: one ${CONFIG.windowKm}x${CONFIG.windowKm} km window, ${d.length} NISAR passes, ${d[0]} to ${d[d.length - 1]}.`;
}
renderAoi();
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

  const dates = new Set();
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
    const feats = Array.isArray(det.data.features) ? det.data.features : [];
    let bad = 0;
    feats.forEach((f) => {
      const p = f?.properties ?? {};
      if (CHECKS.date(p.date)) dates.add(p.date); else bad++;
      if (p.stage !== 'early' && p.stage !== 'late') bad++;
    });
    if (!Array.isArray(det.data.features)) $('s-det').textContent = 'features is missing';
    else if (bad) $('s-det').textContent = `${bad} unexpected date/stage value(s)`;
  } else $('s-det').textContent = failMsg('detections.geojson', det);

  addWindowOutline(); // above the detections and reference layers

  const m = renderAccuracy(metrics);
  const s = renderSummary(summary);
  (m.dates ?? []).forEach((d) => dates.add(d));
  (s.dates ?? []).forEach((d) => dates.add(d));
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

const f2 = (v) => v.toFixed(2);
const ha = (v) => `${v.toFixed(1)} ha`;

function kvList(rows) {
  const dl = el('dl', undefined, 'kv');
  rows.forEach(([k, v]) => { dl.append(el('dt', k), el('dd', String(v))); });
  return dl;
}

// metrics.json: {agreement:{precision_like, recall_like, f1_like, level, split}|null,
//   hand_labeled:{n_sample, precision, n_unsure}|null, n_detections, n_reference, tile, dates, reference_source, notes}
// Returns {dates} for the date slider.
function renderAccuracy(res) {
  const box = $('metrics');
  box.replaceChildren();
  box.classList.remove('missing');
  if (!res.data) { box.classList.add('missing'); box.textContent = failMsg('metrics.json', res); return {}; }

  const problems = [];
  const m = readFields(res.data, {
    agreement: 'obj', hand_labeled: 'obj', n_detections: 'count', n_reference: 'count',
    tile: 'str', dates: 'dates', reference_source: 'str', notes: 'str',
  }, '', problems);

  box.append(el('p', 'Agreement with RADD/GLAD alerts, a reference, not ground truth.', 'caption'));

  // Agreement: refuse to show numbers unless it was scored on the holdout split.
  if ('agreement' in m) {
    if (m.agreement === null) problems.push('agreement is null (skipped)');
    else {
      const a = readFields(m.agreement, {
        precision_like: 'unit', recall_like: 'unit', f1_like: 'unit', level: 'str', split: 'str',
      }, 'agreement.', problems);
      if (a.split === undefined) box.append(el('p', 'agreement numbers not shown: split is missing', 'missing'));
      else if (a.split !== 'holdout') box.append(el('p', `scored on the wrong split (split: ${a.split})`, 'missing'));
      else {
        const rows = [['Split', a.split]];
        if ('level' in a) rows.push(['Level', a.level]);
        if ('precision_like' in a) rows.push(['Precision-like', f2(a.precision_like)]);
        if ('recall_like' in a) rows.push(['Recall-like', f2(a.recall_like)]);
        if ('f1_like' in a) rows.push(['F1-like', f2(a.f1_like)]);
        box.append(kvList(rows));
      }
    }
  }

  // Hand-labeled sample: null means it has not been done yet.
  if ('hand_labeled' in m) {
    box.append(el('h3', 'Hand-labeled sample', 'hint'));
    if (m.hand_labeled === null) box.append(el('p', 'hand-labeled sample pending', 'missing'));
    else {
      const h = readFields(m.hand_labeled, { n_sample: 'count', precision: 'unit', n_unsure: 'count' }, 'hand_labeled.', problems);
      const rows = [];
      if ('precision' in h) rows.push(['Precision', f2(h.precision)]);
      if ('n_sample' in h) rows.push(['n_sample', h.n_sample]);
      if ('n_unsure' in h) rows.push(['n_unsure', h.n_unsure]);
      if (rows.length) box.append(kvList(rows));
    }
  }

  const info = [];
  if ('tile' in m) info.push(['Tile', m.tile]);
  if ('reference_source' in m) info.push(['Reference', m.reference_source]);
  if ('n_detections' in m) info.push(['Detections', m.n_detections]);
  if ('n_reference' in m) info.push(['Reference alerts', m.n_reference]);
  if (info.length) box.append(kvList(info));
  if (m.notes) box.append(el('p', m.notes, 'hint'));

  const pl = problemList('metrics.json', problems);
  if (pl) box.append(pl);
  return { dates: m.dates };
}

// summary.json: {dates:[...], per_date:[{date, n_detections, total_area_ha, early_ha, late_ha}], tuning:{split, hh_thresh, hv_thresh}}
// Returns {dates} for the date slider.
function renderSummary(res) {
  const box = $('summary');
  box.replaceChildren();
  box.classList.remove('missing');
  if (!res.data) { box.classList.add('missing'); box.textContent = failMsg('summary.json', res); return {}; }

  const problems = [];
  const s = readFields(res.data, { dates: 'dates', per_date: 'rows', tuning: 'obj' }, '', problems);

  const rows = [];
  (s.per_date ?? []).forEach((r, i) => {
    const before = problems.length;
    const row = readFields(r, {
      date: 'date', n_detections: 'count', total_area_ha: 'nonneg', early_ha: 'nonneg', late_ha: 'nonneg',
    }, `per_date[${i}].`, problems);
    if (problems.length === before) rows.push(row);
    else problems.push(`per_date[${i}] left out of totals and chart`);
  });
  rows.sort((a, b) => a.date.localeCompare(b.date));

  if (rows.length) {
    const sum = (k) => rows.reduce((t, r) => t + r[k], 0);
    box.append(el('p', 'Totals (sum of per_date rows)', 'hint'));
    box.append(kvList([
      ['Detections', sum('n_detections')],
      ['Total area', ha(sum('total_area_ha'))],
      ['Early stage', ha(sum('early_ha'))],
      ['Late stage', ha(sum('late_ha'))],
    ]));
    box.append(barChart(rows));
  } else if ('per_date' in s) box.append(el('p', 'no valid per_date rows', 'missing'));

  if ('tuning' in s) {
    box.append(el('h3', 'Tuning split', 'hint'));
    if (s.tuning === null) box.append(el('p', 'tuning split not recorded (tuning is null)', 'missing'));
    else {
      const t = readFields(s.tuning, { split: 'str', hh_thresh: 'num', hv_thresh: 'num' }, 'tuning.', problems);
      const trows = [];
      if ('split' in t) trows.push(['Split', t.split]);
      if ('hh_thresh' in t) trows.push(['HH threshold', `${t.hh_thresh} dB`]);
      if ('hv_thresh' in t) trows.push(['HV threshold', `${t.hv_thresh} dB`]);
      if (trows.length) box.append(kvList(trows));
    }
  }

  const pl = problemList('summary.json', problems);
  if (pl) box.append(pl);
  return { dates: [...new Set([...(s.dates ?? []), ...rows.map((r) => r.date)])] };
}

// One stacked bar per date: early vs late hectares.
function barChart(rows) {
  const max = Math.max(...rows.map((r) => r.early_ha + r.late_ha), 1e-9);
  const chart = el('div', undefined, 'chart');
  chart.setAttribute('role', 'img');
  chart.setAttribute('aria-label', 'Hectares of detected disturbance by date, early versus late stage');
  rows.forEach((r) => {
    const row = el('div', undefined, 'bar-row');
    const bar = el('div', undefined, 'bar');
    const e = el('span', undefined, 'early');
    const l = el('span', undefined, 'late');
    e.style.width = `${(r.early_ha / max) * 100}%`;
    l.style.width = `${(r.late_ha / max) * 100}%`;
    e.title = `early ${r.early_ha.toFixed(1)} ha`;
    l.title = `late ${r.late_ha.toFixed(1)} ha`;
    bar.append(e, l);
    row.append(el('span', r.date), bar, el('span', ha(r.early_ha + r.late_ha), 'tot'));
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
