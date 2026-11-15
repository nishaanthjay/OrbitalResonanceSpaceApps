// explore.js : NISAR surface-change explorer. Reads only files written by web/tools/make_explore.py.
// No data is invented here: every pixel and number comes from web/data/explore/ or validation/fnf_metrics.json values
// copied into the story text below (with the file named).
'use strict';

const DATA = 'data/explore/';
const R = 6378137;
const $ = (id) => document.getElementById(id);
const state = { manifest: null, loc: null, i: 0, layer: 'composite', series: null, playing: null, marker: null,
  last: null, det: null, ref: null, hansen: null, metrics: null, big: null, bigMeta: null, lost: null, bigProt: null };
const isBig = () => !!state.loc && state.loc.kind === 'big';
const findLoc = (id) => (state.big && id === state.big.id ? state.big : state.manifest.locations.find((l) => l.id === id));
const COLORS = { early: '#b68b52', late: '#bd776a', ref: '#81989c' };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [-54.699, -8.1995],
  zoom: 11,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

function merc(lon, lat) {
  return [R * lon * Math.PI / 180, R * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))];
}
function corners(b) { // b = W S E N
  return [[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]];
}
function hasImage(layer, i) { return !(layer.endsWith('chg') && i === 0); }
function url(layer, i) {
  if (layer === 'median') return `${DATA}${state.loc.id}/forest_median.webp`;
  return `${DATA}${state.loc.id}/${layer}_${state.loc.dates[i]}.webp`;
}

function setImage() {
  const loc = state.loc, c = corners(loc.bounds_lonlat), op = +$('opacity').value / 100;
  if (isBig()) {
    map.getSource('radar').updateImage({ url: url(state.layer, state.i), coordinates: c });
    map.setPaintProperty('radar', 'raster-opacity', op);
    map.setPaintProperty('chg', 'raster-opacity', 0);
    $('datelabel').textContent = state.layer === 'median' ? `9-pass median (${loc.dates[0]} to ${loc.dates[loc.dates.length - 1]}); slider marks ${loc.dates[state.i]}` : loc.dates[state.i];
    drawLegend();
    redrawLast();
    return;
  }
  const isChg = state.layer.endsWith('chg');
  // base radar image: the chosen layer, or HV under a change layer
  map.getSource('radar').updateImage({ url: url(isChg ? 'hv' : state.layer, state.i), coordinates: c });
  map.setPaintProperty('radar', 'raster-opacity', isChg ? 0.45 * op : op);
  const showChg = isChg && hasImage(state.layer, state.i);
  if (showChg) map.getSource('chg').updateImage({ url: url(state.layer, state.i), coordinates: c });
  map.setPaintProperty('chg', 'raster-opacity', showChg ? 1 : 0);
  $('datelabel').textContent = loc.dates[state.i] + (isChg && !showChg ? '  (first date: nothing earlier to compare)' : '');
  drawLegend();
  updateFilters();
  redrawLast();
}

function preload() { // so the slider and play are smooth
  if (isBig()) { state.loc.dates.forEach((_, i) => { const im = new Image(); im.src = url('forest', i); }); return; }
  for (const layer of ['composite', 'hv', 'hh', 'hvchg', 'hhchg'])
    state.loc.dates.forEach((_, i) => { if (hasImage(layer, i)) { const im = new Image(); im.src = url(layer, i); } });
}

function drawLegend() {
  const s = state.loc.stretch, L = state.layer, el = $('legend');
  if (isBig()) {
    el.innerHTML = `<div class="note keyrow"><span class="sw" style="background:#2f6b4f"></span> forest (HV &ge; ${state.bigMeta.T_db.toFixed(2)} dB) <span class="sw" style="background:#b4401c"></span> non-forest. Transparent = outside the swath on at least one pass. 100 m blocks.</div>`;
    return;
  }
  const bar = (css, lo, hi, unit) => `<div class="legend" style="background:${css}"></div><div class="legend-lab"><span>${lo}</span><span>${hi}</span></div><div class="note">${unit}</div>`;
  if (L === 'hv' || L === 'hh') el.innerHTML = bar('linear-gradient(90deg,#000,#fff)', `${s[L].lo} dB`, `${s[L].hi} dB`, `${L.toUpperCase()} gamma0, one fixed stretch for all dates (values outside are clipped)`);
  else if (L.endsWith('chg')) el.innerHTML = bar('linear-gradient(90deg,#00f,#fff,#f00)', `-${state.manifest.change_range_db} dB (drop)`, `+${state.manifest.change_range_db} dB (rise)`, 'This date minus the mean of all earlier dates. Computed on ~80 m cells; changes under 1 dB are transparent (per-date noise ~0.4 dB at 20 m). Display preview from the clipped layers: real drops can be larger.');
  else el.innerHTML = `<div class="note">Red = HH (${s.hh.lo} to ${s.hh.hi} dB), green = HV (${s.hv.lo} to ${s.hv.hi} dB), blue = HH&minus;HV (${s.ratio.lo} to ${s.ratio.hi} dB). Green/yellow = forest, purple/blue = cleared or bare.</div>`;
}

// ---------- time series ----------
async function loadSeries() {
  const loc = state.loc;
  state.series = null;
  if (loc.kind === 'big') return; // no per-pixel series file for the 60 km map; lost patches carry their own
  try {
    const r = await fetch(`${DATA}${loc.id}/series.bin`);
    if (!r.ok) throw new Error('Series unavailable');
    const bytes = new Uint8Array(await r.arrayBuffer());
    if (bytes.length !== loc.series_shape.reduce((a,b) => a*b, 1)) throw new Error('Invalid series size');
    if (state.loc === loc) state.series = bytes;
  } catch {
    if (state.loc === loc) $('chart').textContent = 'Pixel time series not available. Detection patch series may still be inspected.';
  }
}
function cellAt(lon, lat) {
  const loc = state.loc, b = loc.bounds_lonlat;
  const [x0, y1] = merc(b[0], b[3]), [x1, y0] = merc(b[2], b[1]), [x, y] = merc(lon, lat);
  const [H, W] = loc.image_px, step = state.manifest.series_step;
  const col = Math.floor((x - x0) / (x1 - x0) * W / step), row = Math.floor((y1 - y) / (y1 - y0) * H / step);
  const [, , SH, SW] = loc.series_shape;
  return (row >= 0 && row < SH && col >= 0 && col < SW) ? [row, col] : null;
}
function valuesAt(row, col) {
  const [P, D, SH, SW] = state.loc.series_shape, s = state.loc.stretch, out = { hh: [], hv: [] };
  ['hh', 'hv'].forEach((pol, p) => {
    for (let d = 0; d < D; d++) {
      const v = state.series[((p * D + d) * SH + row) * SW + col];
      out[pol].push(v === 0 ? null : { db: s[pol].lo + (v - 1) / 254 * (s[pol].hi - s[pol].lo), clipped: v === 1 || v === 255 });
    }
  });
  return out;
}

// One chart for both a map click (series.bin cell) and a detection click (full-precision series).
// v = {hh: [...], hv: [...]} of null | {db, clipped}, one per location date.
function chartSVG(v, ref, dates) {
  const all = [...v.hh, ...v.hv].filter(Boolean).map((p) => p.db).concat(ref.hh, ref.hv);
  const lo = Math.floor(Math.min(...all)) - 1, hi = Math.ceil(Math.max(...all)) + 1;
  const W = 340, H = 190, ml = 34, mr = 8, mt = 10, mb = 26;
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[dates.length - 1]);
  const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr);
  const Y = (db) => mt + (hi - db) / (hi - lo) * (H - mt - mb);
  const line = (vals, color, dash) => {
    const pts = vals.map((p, i) => (p == null ? null : [X(dates[i]), Y(typeof p === 'number' ? p : p.db)])).filter(Boolean);
    return `<polyline fill="none" stroke="${color}" stroke-width="2" ${dash ? 'stroke-dasharray="4 3" opacity=".8"' : ''} points="${pts.map((q) => q.join(',')).join(' ')}"/>`;
  };
  const dots = (vals, color) => vals.map((p, i) => (p ? `<circle cx="${X(dates[i])}" cy="${Y(p.db)}" r="${p.clipped ? 4 : 3}" fill="${p.clipped ? '#111' : color}" stroke="${color}" stroke-width="1.5"/>` : '')).join('');
  let grid = '';
  for (let g = Math.ceil(lo); g <= hi; g += 2) grid += `<line x1="${ml}" x2="${W - mr}" y1="${Y(g)}" y2="${Y(g)}" stroke="#333"/><text x="${ml - 4}" y="${Y(g) + 4}" fill="#9aa0a6" font-size="10" text-anchor="end">${g}</text>`;
  const ticks = dates.map((d, i) => (i % 2 === 0 ? `<text x="${X(d)}" y="${H - 8}" fill="#9aa0a6" font-size="10" text-anchor="middle">${d.slice(5)}</text>` : '')).join('');
  const cur = `<line x1="${X(dates[state.i])}" x2="${X(dates[state.i])}" y1="${mt}" y2="${H - mb}" stroke="#fdd663" stroke-dasharray="2 2"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="HH and HV backscatter over time at the clicked spot">${grid}${ticks}${cur}
    ${line(ref.hh, '#bd998d', true)}${line(ref.hv, '#8fa58b', true)}${line(v.hh, '#bd998d')}${line(v.hv, '#8fa58b')}${dots(v.hh, '#bd998d')}${dots(v.hv, '#8fa58b')}</svg>`;
}
function placeMarker(lon, lat) {
  if (state.marker) state.marker.setLngLat([lon, lat]); else { const point = document.createElement('div'); point.className = 'map-point'; point.setAttribute('aria-label','Selected observation'); state.marker = new maplibregl.Marker({ element: point }).setLngLat([lon, lat]).addTo(map); }
}

function drawChart(lon, lat) {
  state.last = { kind: 'point', lon, lat };
  if (isBig()) { $('chart').innerHTML = '<div class="hint">Click a red "forest lost" patch to see its HV series against the forest threshold.</div>'; return; }
  const c = cellAt(lon, lat), el = $('chart');
  if (!c) { el.innerHTML = '<div class="hint">Outside the radar window. Click inside the image.</div>'; return; }
  if (!state.series) { el.textContent = 'Pixel time series not available. Try a detection patch or reload.'; return; }
  const v = valuesAt(...c), ref = state.loc.stable_forest_ref;
  if (!v.hv.some(Boolean)) { el.innerHTML = '<div class="hint">No radar data at this spot.</div>'; return; }
  const clippedAny = [...v.hh, ...v.hv].some((p) => p && p.clipped);
  el.innerHTML = `${chartSVG(v, ref, state.loc.dates)}
    <div class="note"><b style="color:#bd998d">HH</b> and <b style="color:#8fa58b">HV</b> (dB) at ${lat.toFixed(4)}, ${lon.toFixed(4)}, ~80 m cell. Dashed = stable radar forest (median of ${ref.n_pixels.toLocaleString()} px with HV &ge; ${state.manifest.t_db_forest.toFixed(2)} dB on every date). Clearing usually shows as HV falling away from the dashed line.</div>
    ${clippedAny ? '<div class="warn">Hollow dots hit the display stretch limit: the true value is at or beyond it.</div>' : ''}`;
  placeMarker(lon, lat);
}

// A clicked detection: the series are patch means of the 5x5-multilooked full-precision stack (detections.geojson).
const SPLIT_NAME = { tune: 'tune half', holdout: 'holdout half', buffer: 'buffer strip' };
function drawDetection(f, lngLat) {
  state.last = { kind: 'det', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates;
  const title = `Detection ${esc(p.id)}: ${esc(p.area_ha)} ha, first seen ${esc(p.first_date)}, ${esc(SPLIT_NAME[p.split] || p.split)}`;
  const series = (a) => (Array.isArray(a) && a.length === dates.length ? a.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null);
  const hh = series(p.hh_series_db), hv = series(p.hv_series_db);
  if (!hh || !hv) {
    el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Series not drawn: hh_series_db and hv_series_db must each hold ${dates.length} numbers (one per date).</div>`;
    return;
  }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh, hv }, state.loc.stable_forest_ref, dates)}
    <div class="note"><b style="color:#bd998d">HH</b> and <b style="color:#8fa58b">HV</b> (dB): mean over this patch from the full-precision stack (5&times;5 multilook), ${esc(p.stage)} stage. Dashed = stable radar forest from the display layers (median of ${state.loc.stable_forest_ref.n_pixels.toLocaleString()} px), for scale only. Whether this patch is clearing or radar noise is not established by the available optical chip check. Independent human review is needed.</div>`;
  placeMarker(lngLat.lng, lngLat.lat);
}
// A clicked lost patch on the 60 km map: patch-mean HV from the stack (lost.geojson hv_series_db) vs the fixed threshold.
function drawLost(f, lngLat) {
  state.last = { kind: 'lost', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates, T = state.bigMeta.T_db;
  const title = `Lost patch ${esc(p.id)}: ${esc(p.area_ha)} ha, non-forest from ${esc(p.first_flagged || 'n/a')}${p.in_original_window ? ', inside the test window' : ''}`;
  const hv = Array.isArray(p.hv_series_db) && p.hv_series_db.length === dates.length ? p.hv_series_db.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null;
  if (!hv) { el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Series not drawn: hv_series_db must hold ${dates.length} numbers.</div>`; return; }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh: dates.map(() => null), hv }, { hh: [], hv: dates.map(() => T) }, dates)}
    <div class="note"><b style="color:#8fa58b">HV</b> (dB): mean over this patch's 100 m blocks from the full-precision stack. Dashed = the fixed forest threshold ${T.toFixed(2)} dB (above = forest). A drop below the line can also come from moisture or speckle; ${p.n_blocks === 1 ? 'this is a single 1 ha block, ' : ''}unverified.</div>`;
  placeMarker(lngLat.lng, lngLat.lat);
}
function redrawLast() {
  const l = state.last;
  if (!l) return;
  if (l.kind === 'lost') {
    const f = state.lost && state.lost.byId.get(l.id);
    if (f) drawLost(f, { lng: l.lon, lat: l.lat });
    return;
  }
  if (l.kind === 'det') {
    const f = state.det && state.det.byId.get(l.id);
    if (f) drawDetection(f, { lng: l.lon, lat: l.lat });
  } else drawChart(l.lon, l.lat);
}

// ---------- story ----------
function story() {
  $('story').innerHTML = `
    <p><b>The new frontier, twice.</b> The place: the forest edge along the BR-163 highway near Novo Progresso, Pará, a frontier town where forest is being cut for cattle pasture (Mongabay; see submission/sources.md). The sensor: NISAR's L-band radar, which sees through the cloud that hides this forest from optical satellites for much of the year.</p>
    <p><b>Radar separates forest from cleared land.</b> One HV threshold, chosen on the north half of the window and tested once on the south half, put 83.1% of 100 m blocks in the same class as the Hansen forest map (kappa 0.66), against 52.4% for calling everything forest. The same threshold, unchanged, scored 95.6% in Rondônia. <span class="note">(validation/fnf_metrics.json; pre-registered in validation/PREREG_fnf.md. This is agreement with an optical map that ends in 2025, not ground truth.)</span></p>
    <p><b>Catching new clearing is harder, and we say so.</b> On the held-out south half, 2 of 57 detections agree with GLAD-L alerts, and 0 of 179 GLAD-L events of 1 ha or more are caught. 92.5% of 2026 GLAD-L alert pixels fall on land Hansen already mapped as cleared 2001&ndash;2025, which our forest-only method excludes by design. By pixel area, 98.0% to 99.1% of our detections fall on Hansen-intact forest. Whether they are new clearing or radar noise is not established by the available optical chip check. Independent human review is needed. Our threshold, 1.0 dB, is the lowest value we tested and is close to the per-date noise (about 0.4 dB standard deviation on stable forest). We make no claim that these detections are clearing. <span class="note">(validation/results_final.md. Agreement with an alert product is a reference, not ground truth.)</span></p>
    <p class="note">We do not claim this stops deforestation or works everywhere. Rain, fire, flooding and selective logging are not handled.</p>`;
}

// ---------- view 4: detections, GLAD-L, Hansen loss, results (files already in web/data; never invented) ----------
// A file that fails to load shows "pending" for that item only.
async function getJSON(path) {
  try { const r = await fetch(path); return r.ok ? await r.json() : null; } catch { return null; }
}
async function fileExists(path) {
  try { return (await fetch(path, { method: 'HEAD' })).ok; } catch { return false; }
}
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
function pending(key, on) { $(`p-${key}`).hidden = !on; $(`t-${key}`).disabled = on; }
function mk(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text; // textContent only: file text is never parsed as HTML
  if (cls) n.className = cls;
  return n;
}

function addHansen(meta) { // same corners as the radar image: the webp was written on the composite's grid
  const spara = state.manifest.locations.find((l) => l.id === 'spara');
  map.addSource('hansen', { type: 'image', url: `${DATA}spara/hansen_loss.webp`, coordinates: corners(spara.bounds_lonlat) });
  map.addLayer({ id: 'hansen', type: 'raster', source: 'hansen', layout: { visibility: 'none' },
    paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest', 'raster-opacity': 0.85 } });
  const lg = $('han-legend');
  lg.replaceChildren(document.createTextNode('transparent = no loss in 2021–2025:'));
  Object.keys(meta.years).sort().forEach((y) => {
    if (!/^#[0-9a-f]{6}$/i.test(meta.years[y])) return;
    const sw = mk('span', undefined, 'sw');
    sw.style.background = meta.years[y];
    lg.append(sw, document.createTextNode(y));
  });
  pending('han', false);
}

function addRef(fc) {
  const feats = (fc && Array.isArray(fc.features) ? fc.features : []).filter((f) => f && f.geometry && f.properties && DATE_RE.test(f.properties.date || ''));
  if (!feats.length) { pending('ref', true); return; }
  map.addSource('ref', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
  map.addLayer({ id: 'ref-line', type: 'line', source: 'ref', layout: { visibility: 'none' }, paint: { 'line-color': COLORS.ref, 'line-width': 0.8, 'line-opacity': 0.9 } });
  pending('ref', false);
}

function addDetections(fc) {
  const feats = (fc && Array.isArray(fc.features) ? fc.features : []).filter((f) => f && f.geometry && f.properties
    && Number.isInteger(f.properties.id) && DATE_RE.test(f.properties.first_date || '')
    && (f.properties.stage === 'early' || f.properties.stage === 'late'));
  if (!feats.length) { pending('det', true); return; }
  state.det = { byId: new Map(feats.map((f) => [f.properties.id, f])) };
  map.addSource('det', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
  map.addLayer({ id: 'det-fill', type: 'fill', source: 'det', layout: { visibility: 'none' },
    paint: { 'fill-color': ['match', ['get', 'stage'], 'early', COLORS.early, 'late', COLORS.late, '#6b7280'], 'fill-opacity': 0.6 } });
  map.addLayer({ id: 'det-line', type: 'line', source: 'det', layout: { visibility: 'none' }, paint: { 'line-color': '#ffffff', 'line-width': 1 } });
  pending('det', false);
  $('t-det').checked = true;
}

function renderResults() {
  const box = $('results'), m = state.metrics, problems = [];
  box.replaceChildren();
  if (!m || typeof m !== 'object') { box.append(mk('span', 'pending', 'tag')); return; }
  box.append(mk('p', 'Agreement with GLAD-L alerts on the held-out south half: a reference, not ground truth.', 'note'));
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  const rows = [];
  const a = m.agreement;
  if (!a || typeof a !== 'object') problems.push('agreement is missing');
  else if (a.split !== 'holdout') {
    box.append(mk('p', a.split === undefined ? 'agreement not shown: split is missing' : `scored on the wrong split (split: ${a.split})`, 'warn'));
  } else {
    rows.push(['Split', 'holdout']);
    for (const [k, label] of [['precision_like', 'Precision-like'], ['recall_like', 'Recall-like']]) {
      if (num(a[k])) rows.push([label, a[k].toFixed(3)]); else problems.push(`agreement.${k} is missing or not a number`);
    }
  }
  for (const [k, label] of [['n_detections', 'Detections scored'], ['n_reference', 'Reference events']]) {
    if (num(m[k])) rows.push([label, String(m[k])]); else problems.push(`${k} is missing or not a number`);
  }
  if (rows.length) {
    const dl = mk('dl', undefined, 'kv');
    rows.forEach(([k, v]) => dl.append(mk('dt', k), mk('dd', v)));
    box.append(dl);
  }
  if (!('hand_labeled' in m)) problems.push('hand_labeled is missing');
  else if (m.hand_labeled === null) box.append(mk('p', 'Optical chip-label precision: pending', 'note'));
  else if (m.hand_labeled && num(m.hand_labeled.precision)) {
    box.append(mk('p', `Optical chip-label precision (AI review): ${m.hand_labeled.precision.toFixed(3)} (sample ${m.hand_labeled.n_sample}, unsure ${m.hand_labeled.n_unsure}; unsure excluded). Not independently human validated.`, 'note'));
  } else problems.push('hand_labeled.precision is missing or not a number');
  if (m.reference_source !== undefined && m.reference_source !== 'GLAD-L') problems.push(`reference_source is ${m.reference_source}, but the caption says GLAD-L`);
  if (problems.length) {
    const ul = mk('ul', undefined, 'problems');
    problems.forEach((p) => ul.append(mk('li', `metrics.json: ${p}`)));
    box.append(ul);
  }
}

async function loadExtras() {
  // start every fetch at once, add the layers in drawing order (Hansen under alerts under detections)
  const pHan = getJSON(`${DATA}spara/hansen_loss.json`), pRef = getJSON('data/reference_alerts.geojson');
  const pDet = getJSON('data/detections.geojson'), pMet = getJSON('data/metrics.json');
  const han = await pHan;
  if (han && han.years && state.manifest.locations.some((l) => l.id === 'spara') && await fileExists(`${DATA}spara/hansen_loss.webp`)) addHansen(han);
  else pending('han', true);
  addRef(await pRef);
  addDetections(await pDet);
  state.metrics = await pMet;
  renderResults();
}

function updateFilters() { // detections from their first date on, alerts from their date on
  if (!state.loc) return;
  const d = state.loc.dates[state.i];
  if (map.getLayer('det-fill')) { const f = ['<=', ['get', 'first_date'], d]; map.setFilter('det-fill', f); map.setFilter('det-line', f); }
  if (map.getLayer('ref-line')) map.setFilter('ref-line', ['<=', ['get', 'date'], d]);
}
function applyVisibility() {
  const spara = !!state.loc && state.loc.id === 'spara';
  const vis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on && spara ? 'visible' : 'none'); };
  vis('hansen', $('t-han').checked);
  vis('ref-line', $('t-ref').checked);
  vis('det-fill', $('t-det').checked);
  vis('det-line', $('t-det').checked);
  const big = isBig();
  const bvis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on && big ? 'visible' : 'none'); };
  bvis('lost-img', $('t-lost').checked);
  bvis('lost-fill', $('t-lost').checked);
  bvis('lost-line', $('t-lost').checked);
  bvis('prot-line', $('t-prot').checked);
  bvis('prot-label', $('t-prot').checked);
  bvis('win-line', $('t-win').checked);
  bvis('win-label', $('t-win').checked);
}

// ---------- 60 km forest map (web/data/explore/big/, written by web/tools/make_big.py and validation/protected_areas.py) ----------
// Every number shown here is read from big.json / big_protected.json (copied there from validation/scale_metrics.json).
const BIG = `${DATA}big/`;
const pct = (v, d = 1) => (typeof v === 'number' && Number.isFinite(v) ? `${(100 * v).toFixed(d)}%` : 'not available');
const int = (v) => (Number.isInteger(v) ? v.toLocaleString() : 'not available');

function renderBigResults(meta) {
  const box = $('big-results'), sc = meta.scores || {};
  box.replaceChildren();
  const fm = sc.forest_map_vs_hansen || {}, al = sc.alerts || {}, lr = sc.loss_rule || {}, bl = sc.blocks || {};
  const rows = [
    ['Forest map (9-pass median) agreeing with Hansen', `${pct(fm.oa)} vs ${pct(fm.all_forest_baseline)} all-forest baseline`],
    ['Kappa', typeof fm.kappa === 'number' ? fm.kappa.toFixed(3) : 'not available'],
    ['Blocks scored (test window excluded)', `${int(bl.scored)} × 1 ha`],
    ['Lost blocks (class-switch rule)', `${int(lr.lost_blocks)} (${int(lr.lost_ha)} ha)`],
  ];
  for (const [src, label] of [['GLAD-L', 'GLAD-L'], ['GLAD-S2', 'GLAD-S2']]) {
    const a = al[src];
    rows.push([`Lost blocks with a ${label} alert`, a ? `${pct(a.lost.precision_like)} vs ${pct(a.control.precision_like, 2)} random stable-forest control` : 'not available']);
  }
  const dl = mk('dl', undefined, 'kv');
  rows.forEach(([k, v]) => dl.append(mk('dt', k), mk('dd', v)));
  box.append(dl);
  const w = sc.alert_windows || {};
  box.append(mk('p', `Alerts dated ${w.precision ? w.precision.join(' to ') : 'n/a'} (±24 days around ${w.reference ? w.reference.join(' to ') : 'n/a'}). Scored once, rules pre-registered in validation/PREREG_scale.md; full numbers in validation/scale_metrics.json.`, 'note'));
}

function renderBigProtected(pj) {
  const box = $('big-protected');
  box.replaceChildren();
  if (!pj || !Array.isArray(pj.areas)) { box.append(mk('span', 'pending', 'tag')); return; }
  const dl = mk('dl', undefined, 'kv');
  pj.areas.forEach((a) => dl.append(mk('dt', `${a.name} (${a.kind.split(' (')[0]})`),
    mk('dd', `${int(a.lost_blocks_inside)} blocks · ${a.lost_ha_inside} ha (${pct(a.lost_share_of_valid_blocks)} of its mapped blocks)`)));
  const o = pj.outside_all_areas || {};
  dl.append(mk('dt', 'Outside all protected areas'), mk('dd', `${int(o.lost_blocks)} blocks (${pct(o.lost_share_of_valid_blocks)} of mapped blocks)`));
  box.append(dl);
  box.append(mk('p', `Whole 60 km map, test window included (${int(pj.total_lost_blocks)} lost blocks). A block counts when its centre is inside the official boundary. Boundaries: FUNAI Terras Indígenas (read 2026-11-14); MMA CNUC 07/2026 has no conservation unit in this area. See submission/sources.md.`, 'note'));
}

function watchlist() {
  return state.lost.features.map((f) => ({ id: f.properties.id, centroid_lon: f.properties.centroid_lon, centroid_lat: f.properties.centroid_lat,
    area_ha: f.properties.area_ha, first_flagged: f.properties.first_flagged }));
}
function saveFile(name, text, type) {
  const a = document.createElement('a'), u = URL.createObjectURL(new Blob([text], { type }));
  a.href = u; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 1000);
}
function downloadWatchlist(kind) {
  const rows = watchlist();
  if (kind === 'geojson') {
    const fc = { type: 'FeatureCollection', name: 'br163_60km_forest_lost_watchlist',
      description: `Lost patches (class-switch rule, ${state.loc.dates[0]}..${state.loc.dates[state.loc.dates.length - 1]}), NISAR HV threshold ${state.bigMeta.T_db.toFixed(2)} dB. first_flagged: ${state.bigMeta.first_flagged_definition}. Unverified radar flags, not confirmed clearing.`,
      features: rows.map((r) => ({ type: 'Feature', properties: r, geometry: { type: 'Point', coordinates: [r.centroid_lon, r.centroid_lat] } })) };
    saveFile('br163_forest_lost_watchlist.geojson', JSON.stringify(fc), 'application/geo+json');
  } else {
    const head = ['id', 'centroid_lon', 'centroid_lat', 'area_ha', 'first_flagged'];
    saveFile('br163_forest_lost_watchlist.csv', [head.join(','), ...rows.map((r) => head.map((k) => r[k] ?? '').join(','))].join('\n') + '\n', 'text/csv');
  }
}

async function loadBig() {
  const [meta, lost, prot, pj] = await Promise.all([getJSON(`${BIG}big.json`), getJSON(`${BIG}lost.geojson`), getJSON(`${BIG}protected.geojson`), getJSON(`${BIG}big_protected.json`)]);
  if (!meta || !Array.isArray(meta.dates) || !Array.isArray(meta.bounds_lonlat)) return;
  state.bigMeta = meta;
  state.big = { id: 'big', kind: 'big', name: 'BR-163 frontier, 60 km (forest map)', dates: meta.dates, bounds_lonlat: meta.bounds_lonlat,
    notes: 'Forest / non-forest from one fixed NISAR HV threshold on every pass (track 2, frame 174, ascending), 100 m blocks; the swath edge cuts the west of the box. Out-of-sample: threshold fixed on a 10 km strip, tested here unchanged. Agreement with Hansen/GLAD, a reference, not ground truth.' };
  $('loc').append(new Option(`${state.big.name} (${meta.dates.length} dates)`, 'big'));
  const c = corners(meta.bounds_lonlat);
  map.addSource('lost-img', { type: 'image', url: `${BIG}${meta.layers.lost}`, coordinates: c });
  map.addLayer({ id: 'lost-img', type: 'raster', source: 'lost-img', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  if (lost && Array.isArray(lost.features)) {
    const feats = lost.features.filter((f) => f && f.geometry && f.properties && Number.isInteger(f.properties.id));
    state.lost = { features: feats, byId: new Map(feats.map((f) => [f.properties.id, f])) };
    map.addSource('lostp', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    map.addLayer({ id: 'lost-fill', type: 'fill', source: 'lostp', layout: { visibility: 'none' }, paint: { 'fill-color': '#b4401c', 'fill-opacity': 0.01 } });
    map.addLayer({ id: 'lost-line', type: 'line', source: 'lostp', layout: { visibility: 'none' }, minzoom: 12, paint: { 'line-color': '#f3b49b', 'line-width': 0.8 } });
    $('dl-geojson').disabled = false; $('dl-csv').disabled = false;
    $('dl-note').textContent = `${feats.length.toLocaleString()} patches; fields: id, centroid lon/lat, area_ha, first_flagged (${meta.first_flagged_definition}). Unverified radar flags.`;
  }
  if (prot && Array.isArray(prot.features)) {
    map.addSource('prot', { type: 'geojson', data: prot });
    map.addLayer({ id: 'prot-line', type: 'line', source: 'prot', layout: { visibility: 'none' }, paint: { 'line-color': '#e8d48a', 'line-width': 1.6 } });
    const labels = { type: 'FeatureCollection', features: prot.features.filter((f) => Number.isFinite(f.properties.label_lon)).map((f) => ({ type: 'Feature', properties: { name: f.properties.name }, geometry: { type: 'Point', coordinates: [f.properties.label_lon, f.properties.label_lat] } })) };
    map.addSource('prot-pt', { type: 'geojson', data: labels });
    map.addLayer({ id: 'prot-label', type: 'symbol', source: 'prot-pt', layout: { visibility: 'none', 'text-field': ['get', 'name'], 'text-size': 13, 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#f1e3a6', 'text-halo-color': '#07150d', 'text-halo-width': 1.5 } });
  } else { $('p-prot').hidden = false; $('t-prot').disabled = true; }
  const b = meta.original_window_bbox, ring = [...corners(b), corners(b)[0]];
  map.addSource('win', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: ring } } });
  map.addLayer({ id: 'win-line', type: 'line', source: 'win', layout: { visibility: 'none' }, paint: { 'line-color': '#fdd663', 'line-width': 1.8, 'line-dasharray': [3, 2] } });
  map.addSource('win-pt', { type: 'geojson', data: { type: 'Feature', properties: { t: 'test window, excluded from scale scores' }, geometry: { type: 'Point', coordinates: [(b[0] + b[2]) / 2, b[3]] } } });
  map.addLayer({ id: 'win-label', type: 'symbol', source: 'win-pt', layout: { visibility: 'none', 'text-field': ['get', 't'], 'text-size': 12, 'text-anchor': 'bottom', 'text-offset': [0, -0.3], 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#fdd663', 'text-halo-color': '#07150d', 'text-halo-width': 1.5 } });
  renderBigResults(meta);
  renderBigProtected(pj);
  $('dl-geojson').onclick = () => downloadWatchlist('geojson');
  $('dl-csv').onclick = () => downloadWatchlist('csv');
}

// ---------- setup ----------
async function selectLoc(id) {
  if (state.playing) { clearInterval(state.playing); state.playing = null; $('play').textContent = 'Play'; $('play').setAttribute('aria-label','Play'); }
  state.loc = findLoc(id);
  const selected = state.loc;
  if (state.marker) { state.marker.remove(); state.marker = null; }
  state.i = state.loc.dates.length - 1;
  state.last = null;
  const sp = state.loc.id === 'spara', big = isBig();
  $('extras').hidden = !sp; $('extras-off').hidden = sp || big; $('big-extras').hidden = !big;
  $('radar-layers').hidden = big; $('big-layers').hidden = !big; $('big-panel').hidden = !big;
  state.layer = big ? 'forest' : (['forest', 'median'].includes(state.layer) ? 'composite' : state.layer);
  document.querySelectorAll('input[name=layer]').forEach((r) => { r.checked = r.value === state.layer; }); $('results-h').hidden = false; $('results').hidden = false;
  applyVisibility();
  $('chart').innerHTML = big ? '<div class="hint">Click a red "forest lost" patch on the 60 km map to see its HV series.</div>' : '<div class="hint">Click the map to see HH and HV over all dates at that spot, next to stable forest.</div>';
  const s = $('date'); s.max = state.loc.dates.length - 1; s.value = state.i;
  $('about').textContent = big ? `${state.loc.name}. ${state.loc.notes}` : `${state.loc.name}. ${state.loc.notes} Change previews and time series are computed from these display layers (web/tools/make_explore.py), not from detect.py.`;
  const b = state.loc.bounds_lonlat;
  if (map.getSource('boundary')) map.getSource('boundary').setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...corners(b), corners(b)[0]]] } });
  map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 30, duration: 0 });
  setImage();
  if (isBig()) preload();
  await loadSeries();
  if (state.loc !== selected) return;
  $('map-status').hidden = true;
}

map.on('load', async () => {
  try {
  // Contextual vector colors only. Radar imagery and evidence colors are unchanged.
  for (const layer of map.getStyle().layers) {
    const water = /water/i.test(layer.id);
    if (layer.type === 'background') map.setPaintProperty(layer.id,'background-color','#0c2115');
    if (layer.type === 'fill') { map.setPaintProperty(layer.id,'fill-color',water ? '#19313a' : '#193426'); map.setPaintProperty(layer.id,'fill-outline-color','#385640'); }
    if (layer.type === 'line') map.setPaintProperty(layer.id,'line-color',water ? '#81989c' : '#627c65');
    if (layer.type === 'symbol' && layer.layout?.['text-field']) { map.setPaintProperty(layer.id,'text-color','#c1cbbd'); map.setPaintProperty(layer.id,'text-halo-color','#07150d'); }
  }
  map.addSource('esri', { type: 'raster', tileSize: 256, maxzoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'] });
  map.addLayer({ id: 'esri', type: 'raster', source: 'esri', layout: { visibility: 'none' } });
  const response = await fetch(DATA + 'explore.json');
  if (!response.ok) throw new Error('Acquisition catalog unavailable');
  state.manifest = await response.json();
  if (!state.manifest.locations?.length) throw new Error('No study areas available');
  const sel = $('loc');
  state.manifest.locations.forEach((l) => sel.append(new Option(`${l.name} (${l.dates.length} dates)`, l.id)));
  const first = state.manifest.locations[0];
  map.addSource('radar', { type: 'image', url: `${DATA}${first.id}/composite_${first.dates[first.dates.length - 1]}.webp`, coordinates: corners(first.bounds_lonlat) });
  map.addLayer({ id: 'radar', type: 'raster', source: 'radar', paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  map.addSource('chg', { type: 'image', url: `${DATA}${first.id}/hvchg_${first.dates[first.dates.length - 1]}.webp`, coordinates: corners(first.bounds_lonlat) });
  map.addLayer({ id: 'chg', type: 'raster', source: 'chg', paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest', 'raster-opacity': 0 } });
  map.addSource('boundary', { type: 'geojson', data: { type:'FeatureCollection',features:[] } });
  map.addLayer({ id:'boundary',type:'line',source:'boundary',paint:{'line-color':'#c4d5ba','line-width':1.5,'line-dasharray':[4,3]} });
  story();
  try { await loadBig(); } catch (e) { console.warn('60 km forest map not loaded', e); }
  try { await loadExtras(); } catch (e) { ['det', 'ref', 'han'].forEach((k) => pending(k, true)); }
  await selectLoc(first.id);
  ['loc','date','opacity','optical','play','boundary','reset-map'].forEach(id => { if ($(id)) $(id).disabled = false; });
  document.querySelectorAll('input[name=layer]').forEach(r => r.disabled = false);
  } catch (e) { $('map-status').hidden = false; $('map-status').textContent = `Map data not available: ${e.message}. Check the data files and reload.`; }
});

$('loc').onchange = (e) => selectLoc(e.target.value).catch(() => { $('map-status').hidden = false; $('map-status').textContent = 'Study area unavailable. Please reload.'; });
$('date').oninput = (e) => { state.i = +e.target.value; setImage(); };
$('opacity').oninput = () => setImage();
$('optical').onchange = (e) => map.setLayoutProperty('esri', 'visibility', e.target.checked ? 'visible' : 'none');
document.querySelectorAll('input[name=layer]').forEach((r) => (r.onchange = () => { state.layer = r.value; setImage(); }));
['det', 'ref', 'han', 'lost', 'prot', 'win'].forEach((k) => ($(`t-${k}`).onchange = applyVisibility));
map.on('click', (e) => {
  if (!state.loc) return;
  if (isBig()) {
    if (state.lost && map.getLayer('lost-fill') && $('t-lost').checked) {
      const r = 4;
      const hits = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]], { layers: ['lost-fill'] })
        .map((h) => state.lost.byId.get(h.properties.id)).filter(Boolean);
      if (hits.length) { hits.sort((a, b) => b.properties.area_ha - a.properties.area_ha); drawLost(hits[0], e.lngLat); return; }
    }
    drawChart(e.lngLat.lng, e.lngLat.lat);
    return;
  }
  if (state.loc && state.loc.id === 'spara' && state.det && map.getLayer('det-fill') && $('t-det').checked) {
    const r = 4; // px tolerance: the patches are small
    const hits = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]], { layers: ['det-fill'] })
      .map((h) => state.det.byId.get(h.properties.id)).filter(Boolean);
    if (hits.length) { // smallest patch first when several overlap
      hits.sort((a, b) => a.properties.area_ha - b.properties.area_ha);
      drawDetection(hits[0], e.lngLat);
      return;
    }
  }
  drawChart(e.lngLat.lng, e.lngLat.lat);
});
$('play').onclick = () => {
  if (!state.loc) return;
  if (state.playing) { clearInterval(state.playing); state.playing = null; $('play').textContent = 'Play'; $('play').setAttribute('aria-label','Play'); return; }
  $('play').textContent = 'Pause'; $('play').setAttribute('aria-label','Pause');
  state.playing = setInterval(() => { state.i = (state.i + 1) % state.loc.dates.length; $('date').value = state.i; setImage(); }, 900);
};

// Controls stay inactive until their map sources exist. Failed layers remain independently inspectable.
['loc','date','opacity','optical','play','boundary','reset-map'].forEach(id => $(id).disabled = true);
document.querySelectorAll('input[name=layer]').forEach(r => r.disabled = true);
$('boundary').onchange = e => map.setLayoutProperty('boundary','visibility',e.target.checked ? 'visible' : 'none');
$('reset-map').onclick = () => { const b = state.loc.bounds_lonlat; map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:30,duration:0}); };
map.on('error', e => { $('map-status').hidden = false; $('map-status').textContent = 'A map layer could not load. Other observations may still be available. Check your connection or try another layer.'; });
new ResizeObserver(() => map.resize()).observe($('map'));
