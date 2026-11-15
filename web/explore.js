// explore.js : NISAR surface-change explorer. Reads only files written by web/tools/make_explore.py.
// No data is invented here: every pixel and number comes from web/data/explore/ or validation/fnf_metrics.json values
// copied into the story text below (with the file named).
'use strict';

const DATA = 'data/explore/';
const R = 6378137;
const FADE = 420; // ms cross-fade between radar passes
const $ = (id) => document.getElementById(id);
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const state = { manifest: null, loc: null, i: 0, layer: 'hv', series: null, playing: null, marker: null, mode: 'intro',
  last: null, det: null, ref: null, hansen: null, metrics: null, big: null, bigMeta: null, lost: null, bigProt: null };
const isBig = () => !!state.loc && state.loc.kind === 'big';
const findLoc = (id) => (state.big && id === state.big.id ? state.big : state.manifest.locations.find((l) => l.id === id));
const COLORS = { early: '#b68b52', late: '#bd776a', ref: '#81989c' };
const CHART = { hh: '#CED9DF', hv: '#93A889', grid: '#3E563E', text: '#7993A0', cur: '#93A889' };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/dark',
  center: [-54.699, -8.1995],
  zoom: 11,
  attributionControl: { compact: true },
  fadeDuration: reduced ? 0 : 300,
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
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

// ---------- cross-fading image layers: each kind has two map layers, the new pass loads into the hidden one ----------
const slots = { radar: { front: 'radarA', back: 'radarB', href: null, token: 0 }, chg: { front: 'chgA', back: 'chgB', href: null, token: 0 } };
function sourceLoaded(id) {
  return new Promise((res) => {
    const done = () => { map.off('sourcedata', h); clearTimeout(t); res(); };
    const h = (e) => { if (e.sourceId === id && e.isSourceLoaded) done(); };
    const t = setTimeout(done, 900);
    map.on('sourcedata', h);
  });
}
async function show(kind, href, opacity) {
  const s = slots[kind];
  if (!href) { s.token++; map.setPaintProperty(s.front, 'raster-opacity', 0); return; }
  if (href === s.href) { map.setPaintProperty(s.front, 'raster-opacity', opacity); return; }
  s.href = href;
  const token = ++s.token, back = s.back;
  const loaded = sourceLoaded(back);
  map.getSource(back).updateImage({ url: href, coordinates: corners(state.loc.bounds_lonlat) });
  await loaded;
  if (token !== s.token) return; // a newer pass was asked for meanwhile
  map.setPaintProperty(back, 'raster-opacity', opacity);
  map.setPaintProperty(s.front, 'raster-opacity', 0);
  [s.front, s.back] = [back, s.front];
}

function setText(el, text) { // a small roll when a label changes
  if (el.textContent === text) return;
  el.textContent = text;
  if (!reduced) el.animate([{ opacity: 0, transform: 'translateY(5px)' }, { opacity: 1, transform: 'none' }], { duration: 280, easing: 'cubic-bezier(.2,.8,.2,1)' });
}

const LAYER_NAME = { hv: 'HV', hh: 'HH', composite: 'HH + HV', hvchg: 'HV change', hhchg: 'HH change', forest: 'forest map', median: 'forest map' };
function setImage(redraw = true) {
  const loc = state.loc, op = +$('opacity').value / 100, date = loc.dates[state.i];
  if (isBig()) {
    show('radar', url(state.layer, state.i), op);
    show('chg', null);
    setText($('datelabel'), state.layer === 'median' ? `9-pass median · ${loc.dates[0]} to ${loc.dates[loc.dates.length - 1]}` : `${date} · pass ${state.i + 1} of ${loc.dates.length}`);
    setText($('hero-what'), state.layer === 'median' ? 'its 9-pass forest map' : `its forest map from ${date}`);
  } else {
    const isChg = state.layer.endsWith('chg');
    // base radar image: the chosen layer, or HV under a change layer
    show('radar', url(isChg ? 'hv' : state.layer, state.i), isChg ? 0.45 * op : op);
    const showChg = isChg && hasImage(state.layer, state.i);
    show('chg', showChg ? url(state.layer, state.i) : null, 1);
    setText($('datelabel'), `${date} · pass ${state.i + 1} of ${loc.dates.length}` + (isChg && !showChg ? ' · first pass, nothing earlier to compare' : ''));
    setText($('hero-what'), `its ${LAYER_NAME[state.layer]} image from ${date}`);
  }
  const exploring = state.mode === 'exploring';
  $('card-radar').setAttribute('aria-current', String(exploring && !isBig() && state.layer === 'composite'));
  $('card-change').setAttribute('aria-current', String(exploring && !isBig() && state.layer === 'hvchg'));
  $('card-big').setAttribute('aria-current', String(exploring && isBig()));
  $('date').value = state.i;
  document.querySelectorAll('.pass').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.i === state.i)));
  const on = document.querySelector('.pass[aria-pressed=true]');
  if (on) $('rail-cursor').style.setProperty('--p', on.style.getPropertyValue('--p'));
  drawLegend();
  updateFilters();
  if (redraw) redrawLast();
}

function preload() { // so the passes and play are smooth
  if (isBig()) { state.loc.dates.forEach((_, i) => { const im = new Image(); im.src = url('forest', i); }); return; }
  for (const layer of ['composite', 'hv', 'hh', 'hvchg', 'hhchg'])
    state.loc.dates.forEach((_, i) => { if (hasImage(layer, i)) { const im = new Image(); im.src = url(layer, i); } });
}

// one tick per pass, placed by date; a dashed slot marks each 12-day repeat with no pass in the stack
function drawPasses() {
  const dates = state.loc.dates, t = dates.map((d) => Date.parse(d)), span = t[t.length - 1] - t[0], DAY = 864e5;
  const x = (ms) => `--p:${(((ms - t[0]) / span) * 100).toFixed(2)}`;
  let html = '<span class="rail-cursor" id="rail-cursor" aria-hidden="true"></span>';
  for (let k = 1; k < t.length; k++)
    for (let g = t[k - 1] + 12 * DAY; g < t[k] - 6 * DAY; g += 12 * DAY) html += `<span class="gap" style="${x(g)}" title="No pass in the stack"></span>`;
  html += dates.map((d, i) => `<button class="pass" style="${x(t[i])};--d:${i}" data-i="${i}" aria-pressed="false" aria-label="Pass ${d}" tabindex="${i === state.i ? 0 : -1}"><i></i><span>${d.slice(5)}</span></button>`).join('');
  $('passes').innerHTML = html;
  $('pass-count').textContent = String(dates.length).padStart(2, '0');
}

// strip facts and thumbnails, all from the manifest and the exported layers
function drawStrip() {
  const d = state.loc.dates, last = d[d.length - 1], first = state.manifest.locations[0], fl = first.dates[first.dates.length - 1];
  const mon = (s) => new Date(s + 'T00:00:00Z').toLocaleString('en', { month: 'short', timeZone: 'UTC' });
  $('facts').innerHTML = `<span><b>L-band</b> radar, ~24 cm waves</span><span><b>${d.length} passes</b> &middot; ${mon(d[0])}&ndash;${mon(last)} ${last.slice(0, 4)}</span>` +
    '<span><b>12-day</b> repeat orbit</span>';
  $('thumb-radar').src = `${DATA}${first.id}/composite_${fl}.webp`;
  $('thumb-change').src = `${DATA}${first.id}/hvchg_${fl}.webp`;
  if (state.big) { $('thumb-big').src = `${DATA}big/forest_median.webp`; $('card-big').hidden = false; }
}

// ---------- intro (hero over the tinted radar) <-> exploring (controls panel) ----------
function padding() {
  const c = map.getContainer(), W = c.clientWidth, H = c.clientHeight, mob = W <= 900;
  return mob ? { top: 110, left: 16, right: 16, bottom: Math.round(H * (state.mode === 'intro' ? 0.5 : 0.58)) }
    : { top: 80, right: 60, bottom: 150, left: state.mode === 'intro' ? Math.round(W * 0.16) : 76 + 372 + 40 };
}
function fit(duration = 1300) {
  if (!state.loc) return;
  const b = state.loc.bounds_lonlat, mob = map.getContainer().clientWidth <= 900;
  const cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padding() });
  if (!cam) return;
  // intro on a wide screen: zoom past the fit so the radar bleeds off the right edge like a photograph
  map.easeTo({ ...cam, zoom: cam.zoom + (state.mode === 'intro' && !mob && !isBig() ? 1.15 : 0), duration: reduced ? 0 : duration, easing: easeInOut });
}
function focusBounds(b) { // b = W S E N of a patch: zoom to it, clear of the panel
  map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padding(), maxZoom: 15, duration: reduced ? 0 : 1100, easing: easeInOut });
}
// in the intro the map is a picture you scroll past; it only takes gestures once you are exploring
const HANDLERS = ['scrollZoom', 'dragPan', 'dragRotate', 'touchZoomRotate', 'doubleClickZoom', 'keyboard', 'boxZoom'];
function setInteractive(on) { HANDLERS.forEach((h) => map[h][on ? 'enable' : 'disable']()); }
setInteractive(false);
map.getCanvas().style.cursor = 'pointer';

function setMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  document.body.classList.toggle('exploring', mode === 'exploring');
  map.getCanvas().style.cursor = mode === 'exploring' ? 'crosshair' : 'pointer'; // intro: a click opens the explorer
  setInteractive(mode === 'exploring');
  if (!state.loc) return;
  applyVisibility();
  fit();
  setImage(false);
}
function toTop() { if (scrollY > 4) scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' }); }
async function go(target) {
  toTop();
  if (target === 'intro') return setMode('intro');
  const first = state.manifest && state.manifest.locations[0];
  if (target === 'big' && state.big) {
    if (!isBig()) { $('loc').value = 'big'; await selectLoc('big'); }
  } else if (['composite', 'hv', 'hh', 'hvchg', 'hhchg'].includes(target)) {
    if (isBig() && first) { $('loc').value = first.id; await selectLoc(first.id); }
    state.layer = target;
    document.querySelectorAll('input[name=layer]').forEach((r) => { r.checked = r.value === target; });
    if (state.mode === 'exploring') setImage();
  }
  setMode('exploring');
}
function goTo(i) {
  state.i = (i + state.loc.dates.length) % state.loc.dates.length;
  document.querySelectorAll('.pass').forEach((b) => (b.tabIndex = +b.dataset.i === state.i ? 0 : -1));
  setImage();
}

function drawLegend() {
  const s = state.loc.stretch, L = state.layer, el = $('legend');
  if (isBig()) {
    el.innerHTML = `<div class="note keyrow" style="padding-left:0"><span class="sw" style="background:#2f6b4f"></span> forest (HV &ge; ${state.bigMeta.T_db.toFixed(2)} dB) <span class="sw" style="background:#b4401c"></span> non-forest. Transparent = outside the swath on at least one pass. 100 m blocks.</div>`;
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
    if (bytes.length !== loc.series_shape.reduce((a, b) => a * b, 1)) throw new Error('Invalid series size');
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
// v = {hh: [...], hv: [...]} of null | {db, clipped}, one per location date. fresh = draw the lines in.
function chartSVG(v, ref, dates, fresh) {
  const all = [...v.hh, ...v.hv].filter(Boolean).map((p) => p.db).concat(ref.hh, ref.hv);
  const lo = Math.floor(Math.min(...all)) - 1, hi = Math.ceil(Math.max(...all)) + 1;
  const W = 340, H = 190, ml = 34, mr = 8, mt = 10, mb = 26;
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[dates.length - 1]);
  const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr);
  const Y = (db) => mt + (hi - db) / (hi - lo) * (H - mt - mb);
  const line = (vals, color, dash) => {
    const pts = vals.map((p, i) => (p == null ? null : [X(dates[i]), Y(typeof p === 'number' ? p : p.db)])).filter(Boolean);
    return `<polyline fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" ${dash ? 'stroke-dasharray="4 3" opacity=".8"' : 'pathLength="1" class="draw"'} points="${pts.map((q) => q.join(',')).join(' ')}"/>`;
  };
  const dots = (vals, color) => vals.map((p, i) => (p ? `<circle class="dot" style="--d:${i}" cx="${X(dates[i])}" cy="${Y(p.db)}" r="${p.clipped ? 4 : 3}" fill="${p.clipped ? '#1F2F22' : color}" stroke="${color}" stroke-width="1.5"/>` : '')).join('');
  let grid = '';
  for (let g = Math.ceil(lo); g <= hi; g += 2) grid += `<line x1="${ml}" x2="${W - mr}" y1="${Y(g)}" y2="${Y(g)}" stroke="${CHART.grid}" stroke-opacity=".5"/><text x="${ml - 4}" y="${Y(g) + 4}" fill="${CHART.text}" font-size="10" text-anchor="end">${g}</text>`;
  const ticks = dates.map((d, i) => (i % 2 === 0 ? `<text x="${X(d)}" y="${H - 8}" fill="${CHART.text}" font-size="10" text-anchor="${i === dates.length - 1 ? 'end' : 'middle'}">${d.slice(5)}</text>` : '')).join('');
  const cur = `<line x1="${X(dates[state.i])}" x2="${X(dates[state.i])}" y1="${mt}" y2="${H - mb}" stroke="${CHART.cur}" stroke-opacity=".7" stroke-dasharray="2 3"/>`;
  return `<svg class="${fresh ? 'fresh' : ''}" viewBox="0 0 ${W} ${H}" role="img" aria-label="HH and HV backscatter over time at the selected spot">${grid}${ticks}${cur}
    ${line(ref.hh, CHART.hh, true)}${line(ref.hv, CHART.hv, true)}${line(v.hh, CHART.hh)}${line(v.hv, CHART.hv)}${dots(v.hh, CHART.hh)}${dots(v.hv, CHART.hv)}</svg>`;
}
function placeMarker(lon, lat, fresh) {
  if (state.marker) state.marker.setLngLat([lon, lat]);
  else {
    const el = document.createElement('div');
    el.className = 'pin';
    el.setAttribute('aria-label', 'Selected observation');
    el.innerHTML = '<span></span>'; // MapLibre positions the outer element with transform; animate the inner one
    state.marker = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(map);
  }
  if (!fresh) return;
  if (!reduced) state.marker.getElement().firstChild.animate([{ transform: 'scale(.3)', opacity: 0 }, { transform: 'scale(1)', opacity: 1 }], { duration: 420, easing: 'cubic-bezier(.3,1.6,.5,1)' });
  setTimeout(() => { // bring the chart into view inside the panel (scrollIntoView would also scroll the page)
    const box = document.querySelector('.side-scroll'), sec = $('chart').closest('section');
    const top = sec.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 8;
    const bottom = top + sec.offsetHeight + 16;
    if (top < box.scrollTop || bottom > box.scrollTop + box.clientHeight) box.scrollTo({ top, behavior: reduced ? 'auto' : 'smooth' });
  }, 250);
}

const KEY = `<b style="color:${CHART.hh}">HH</b> and <b style="color:${CHART.hv}">HV</b>`;
function drawChart(lon, lat, fresh = true) {
  state.last = { kind: 'point', lon, lat };
  if (isBig()) { $('chart').innerHTML = '<div class="hint">Click a red "forest lost" patch to see its HV series against the forest threshold.</div>'; return; }
  const c = cellAt(lon, lat), el = $('chart');
  if (!c) { el.innerHTML = '<div class="hint">Outside the radar window. Click inside the image.</div>'; return; }
  if (!state.series) { el.textContent = 'Pixel time series not available. Try a detection patch or reload.'; return; }
  const v = valuesAt(...c), ref = state.loc.stable_forest_ref;
  if (!v.hv.some(Boolean)) { el.innerHTML = '<div class="hint">No radar data at this spot.</div>'; return; }
  const clippedAny = [...v.hh, ...v.hv].some((p) => p && p.clipped);
  el.innerHTML = `${chartSVG(v, ref, state.loc.dates, fresh)}
    <div class="note">${KEY} (dB) at ${lat.toFixed(4)}, ${lon.toFixed(4)}, ~80 m cell. Dashed = stable radar forest (median of ${ref.n_pixels.toLocaleString()} px with HV &ge; ${state.manifest.t_db_forest.toFixed(2)} dB on every date). Clearing usually shows as HV falling away from the dashed line.</div>
    ${clippedAny ? '<div class="warn">Hollow dots hit the display stretch limit: the true value is at or beyond it.</div>' : ''}`;
  placeMarker(lon, lat, fresh);
}

// A clicked detection: the series are patch means of the 5x5-multilooked full-precision stack (detections.geojson).
const SPLIT_NAME = { tune: 'tune half', holdout: 'holdout half', buffer: 'buffer strip' };
function drawDetection(f, lngLat, fresh = true) {
  state.last = { kind: 'det', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates;
  const title = `Detection ${esc(p.id)}: ${esc(p.area_ha)} ha, first seen ${esc(p.first_date)}, ${esc(SPLIT_NAME[p.split] || p.split)}`;
  const series = (a) => (Array.isArray(a) && a.length === dates.length ? a.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null);
  const hh = series(p.hh_series_db), hv = series(p.hv_series_db);
  if (!hh || !hv) {
    el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Series not drawn: hh_series_db and hv_series_db must each hold ${dates.length} numbers (one per date).</div>`;
    return;
  }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh, hv }, state.loc.stable_forest_ref, dates, fresh)}
    <div class="note">${KEY} (dB): mean over this patch from the full-precision stack (5&times;5 multilook), ${esc(p.stage)} stage. Dashed = stable radar forest from the display layers (median of ${state.loc.stable_forest_ref.n_pixels.toLocaleString()} px), for scale only. Whether this patch is clearing or radar noise is not established by the available optical chip check. Independent human review is needed.</div>`;
  placeMarker(lngLat.lng, lngLat.lat, fresh);
}
// A clicked lost patch on the 60 km map: patch-mean HV from the stack (lost.geojson hv_series_db) vs the fixed threshold.
function drawLost(f, lngLat, fresh = true) {
  state.last = { kind: 'lost', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates, T = state.bigMeta.T_db;
  const title = `Lost patch ${esc(p.id)}: ${esc(p.area_ha)} ha, non-forest from ${esc(p.first_flagged || 'n/a')}${p.in_original_window ? ', inside the test window' : ''}`;
  const hv = Array.isArray(p.hv_series_db) && p.hv_series_db.length === dates.length ? p.hv_series_db.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null;
  if (!hv) { el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Series not drawn: hv_series_db must hold ${dates.length} numbers.</div>`; return; }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh: dates.map(() => null), hv }, { hh: [], hv: dates.map(() => T) }, dates, fresh)}
    <div class="note"><b style="color:${CHART.hv}">HV</b> (dB): mean over this patch's 100 m blocks from the full-precision stack. Dashed = the fixed forest threshold ${T.toFixed(2)} dB (above = forest). A drop below the line can also come from moisture or speckle; ${p.n_blocks === 1 ? 'this is a single 1 ha block, ' : ''}unverified.</div>`;
  placeMarker(lngLat.lng, lngLat.lat, fresh);
}
function redrawLast() { // same selection, new pass: redraw without the entrance animation
  const l = state.last;
  if (!l) return;
  if (l.kind === 'lost') {
    const f = state.lost && state.lost.byId.get(l.id);
    if (f) drawLost(f, { lng: l.lon, lat: l.lat }, false);
    return;
  }
  if (l.kind === 'det') {
    const f = state.det && state.det.byId.get(l.id);
    if (f) drawDetection(f, { lng: l.lon, lat: l.lat }, false);
  } else drawChart(l.lon, l.lat, false);
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
    sw.style.marginLeft = '6px';
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
function applyVisibility() { // evidence overlays only while exploring: the intro shows the radar alone
  const ex = state.mode === 'exploring', spara = !!state.loc && state.loc.id === 'spara';
  if (map.getLayer('boundary')) map.setLayoutProperty('boundary', 'visibility', ex && $('boundary').checked ? 'visible' : 'none');
  const vis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on && ex && spara ? 'visible' : 'none'); };
  vis('hansen', $('t-han').checked);
  vis('ref-line', $('t-ref').checked);
  vis('det-fill', $('t-det').checked);
  vis('det-line', $('t-det').checked);
  const big = isBig();
  const bvis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on && ex && big ? 'visible' : 'none'); };
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
    map.addLayer({ id: 'prot-label', type: 'symbol', source: 'prot-pt', layout: { visibility: 'none', 'text-field': ['get', 'name'], 'text-size': 13, 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#f1e3a6', 'text-halo-color': '#091008', 'text-halo-width': 1.5 } });
  } else { $('p-prot').hidden = false; $('t-prot').disabled = true; }
  const b = meta.original_window_bbox, ring = [...corners(b), corners(b)[0]];
  map.addSource('win', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: ring } } });
  map.addLayer({ id: 'win-line', type: 'line', source: 'win', layout: { visibility: 'none' }, paint: { 'line-color': '#fdd663', 'line-width': 1.8, 'line-dasharray': [3, 2] } });
  map.addSource('win-pt', { type: 'geojson', data: { type: 'Feature', properties: { t: 'test window, excluded from scale scores' }, geometry: { type: 'Point', coordinates: [(b[0] + b[2]) / 2, b[3]] } } });
  map.addLayer({ id: 'win-label', type: 'symbol', source: 'win-pt', layout: { visibility: 'none', 'text-field': ['get', 't'], 'text-size': 12, 'text-anchor': 'bottom', 'text-offset': [0, -0.3], 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#fdd663', 'text-halo-color': '#091008', 'text-halo-width': 1.5 } });
  renderBigResults(meta);
  renderBigProtected(pj);
  $('dl-geojson').onclick = () => downloadWatchlist('geojson');
  $('dl-csv').onclick = () => downloadWatchlist('csv');
}

// ---------- setup ----------
function stopPlay() {
  if (!state.playing) return;
  clearInterval(state.playing); state.playing = null;
  $('play').classList.remove('playing');
  $('play-ico').innerHTML = PLAY;
  setText($('play-txt'), 'Play passes');
  $('play').setAttribute('aria-label', 'Play through the passes');
}
async function selectLoc(id) {
  stopPlay();
  state.loc = findLoc(id);
  const selected = state.loc;
  if (state.marker) { state.marker.remove(); state.marker = null; }
  state.i = state.loc.dates.length - 1;
  state.last = null;
  slots.radar.href = slots.chg.href = null;
  const sp = state.loc.id === 'spara', big = isBig();
  $('extras').hidden = !sp; $('extras-off').hidden = sp || big; $('big-extras').hidden = !big;
  $('radar-layers').hidden = big; $('big-layers').hidden = !big; $('big-panel').hidden = !big;
  state.layer = big ? 'forest' : (['forest', 'median'].includes(state.layer) ? 'hv' : state.layer);
  document.querySelectorAll('input[name=layer]').forEach((r) => { r.checked = r.value === state.layer; });
  applyVisibility();
  $('chart').innerHTML = big ? '<div class="hint">Click a red "forest lost" patch on the 60 km map to see its HV series.</div>' : '<div class="hint">Click the map to see HH and HV over all dates at that spot, next to stable forest.</div>';
  const s = $('date'); s.max = state.loc.dates.length - 1; s.value = state.i;
  drawPasses();
  drawStrip();
  $('about').textContent = big ? `${state.loc.name}. ${state.loc.notes}` : `${state.loc.name}. ${state.loc.notes} Change previews and time series are computed from these display layers (web/tools/make_explore.py), not from detect.py.`;
  const b = state.loc.bounds_lonlat;
  if (map.getSource('boundary')) map.getSource('boundary').setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...corners(b), corners(b)[0]]] } });
  fit(state.mode === 'intro' ? 0 : 1100);
  setImage();
  preload();
  await loadSeries();
  if (state.loc !== selected) return;
  $('map-status').hidden = true;
}

map.on('load', async () => {
  try {
    // tint the dark basemap to the page palette (canopy ground, understory water); radar and evidence colors are unchanged
    for (const l of map.getStyle().layers) {
      if (l.type === 'background') map.setPaintProperty(l.id, 'background-color', '#091008');
      else if (l.type === 'fill' && /water/.test(l.id)) map.setPaintProperty(l.id, 'fill-color', '#1F2F22');
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
    const first = state.manifest.locations[0], c0 = corners(first.bounds_lonlat), d0 = first.dates[first.dates.length - 1];
    const paint = { 'raster-fade-duration': 0, 'raster-resampling': 'nearest', 'raster-opacity': 0, 'raster-opacity-transition': { duration: reduced ? 0 : FADE, delay: 0 } };
    for (const id of ['radarA', 'radarB']) {
      map.addSource(id, { type: 'image', url: `${DATA}${first.id}/hv_${d0}.webp`, coordinates: c0 });
      map.addLayer({ id, type: 'raster', source: id, paint });
    }
    for (const id of ['chgA', 'chgB']) {
      map.addSource(id, { type: 'image', url: `${DATA}${first.id}/hvchg_${d0}.webp`, coordinates: c0 });
      map.addLayer({ id, type: 'raster', source: id, paint });
    }
    map.addSource('boundary', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'boundary', type: 'line', source: 'boundary', paint: { 'line-color': '#93A889', 'line-opacity': 0.7, 'line-width': 1.2, 'line-dasharray': [4, 3] } });
    story();
    try { await loadBig(); } catch (e) { console.warn('60 km forest map not loaded', e); }
    try { await loadExtras(); } catch (e) { ['det', 'ref', 'han'].forEach((k) => pending(k, true)); }
    await selectLoc(first.id);
    ['loc', 'date', 'opacity', 'optical', 'play', 'boundary', 'reset-map'].forEach((id) => { if ($(id)) $(id).disabled = false; });
    document.querySelectorAll('input[name=layer]').forEach((r) => (r.disabled = false));
    document.body.classList.add('ready');
    // phones: keep the map credits behind the (i) button so they do not cover the hero
    if (innerWidth <= 900) document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
  } catch (e) { $('map-status').hidden = false; $('map-status').textContent = `Map data not available: ${e.message}. Check the data files and reload.`; }
});

$('loc').onchange = (e) => selectLoc(e.target.value).catch(() => { $('map-status').hidden = false; $('map-status').textContent = 'Study area unavailable. Please reload.'; });
$('date').oninput = (e) => goTo(+e.target.value);
$('passes').onclick = (e) => { const b = e.target.closest('.pass'); if (b) goTo(+b.dataset.i); };
$('passes').onkeydown = (e) => {
  const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
  if (!step) return;
  e.preventDefault();
  goTo(state.i + step);
  document.querySelector(`.pass[data-i="${state.i}"]`).focus();
};
$('opacity').oninput = () => setImage(false);
$('optical').onchange = (e) => map.setLayoutProperty('esri', 'visibility', e.target.checked ? 'visible' : 'none');
document.querySelectorAll('input[name=layer]').forEach((r) => (r.onchange = () => { state.layer = r.value; setImage(); }));
['det', 'ref', 'han', 'lost', 'prot', 'win'].forEach((k) => ($(`t-${k}`).onchange = applyVisibility));
map.on('click', (e) => {
  if (!state.loc) return;
  setMode('exploring');
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
  if (state.loc.id === 'spara' && state.det && map.getLayer('det-fill') && $('t-det').checked) {
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
document.querySelectorAll('[data-go]').forEach((el) => (el.onclick = (e) => { e.preventDefault(); go(el.dataset.go); }));
map.on('resize', () => { if (state.mode === 'intro') fit(0); });
addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.mode === 'exploring') setMode('intro'); });
const PLAY = '<path d="M1 1l10 6-10 6z" fill="currentColor"/>', PAUSE = '<path d="M1 1h3v12H1zM8 1h3v12H8z" fill="currentColor"/>';
$('play').onclick = () => {
  if (!state.loc) return;
  if (state.playing) return stopPlay();
  state.playing = setInterval(() => goTo(state.i + 1), 1100);
  $('play').classList.add('playing');
  $('play-ico').innerHTML = PAUSE;
  setText($('play-txt'), 'Pause');
  $('play').setAttribute('aria-label', 'Pause');
};

// Controls stay inactive until their map sources exist. Failed layers remain independently inspectable.
['loc', 'date', 'opacity', 'optical', 'play', 'boundary', 'reset-map'].forEach((id) => ($(id).disabled = true));
document.querySelectorAll('input[name=layer]').forEach((r) => (r.disabled = true));
$('boundary').onchange = applyVisibility;
$('reset-map').onclick = () => fit();
map.on('error', () => { $('map-status').hidden = false; $('map-status').textContent = 'A map layer could not load. Other observations may still be available. Check your connection or try another layer.'; });
