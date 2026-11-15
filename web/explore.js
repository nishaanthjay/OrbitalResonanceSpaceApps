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
  last: null, det: null, ref: null, hansen: null, metrics: null, big: null, bigMeta: null, lost: null, bigProt: null, frame: null, frameMeta: null, frameLost: null };
const isBig = () => !!state.loc && state.loc.kind === 'big';
const isFrame = () => !!state.loc && state.loc.kind === 'frame';
const isForestLoc = () => isBig() || isFrame(); // forest-map locations (no radar layers, no pixel series)
const findLoc = (id) => (state.big && id === state.big.id ? state.big : state.frame && id === state.frame.id ? state.frame
  : state.manifest.locations.find((l) => l.id === id));
const lostSet = () => (isFrame() ? state.frameLost : isBig() ? state.lost : null);
const STATIC_LAYERS = { median: 'forest_median.webp', confidence: 'confidence.webp', persistence: 'persistence.webp' };
const LAYERS_FOR = { big: ['forest', 'median', 'confidence', 'persistence'], frame: ['median'] };
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
  if (STATIC_LAYERS[layer]) return `${DATA}${state.loc.id}/${STATIC_LAYERS[layer]}`;
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

const LAYER_NAME = { hv: 'tree-signal', hh: 'ground-signal', composite: 'colour-mix', hvchg: 'tree-signal change', hhchg: 'ground-signal change', forest: 'forest map', median: 'typical forest map', confidence: 'map of unsure squares', persistence: 'count of passes seen as forest' };
const STATIC_LABEL = { median: 'typical forest map', confidence: 'unsure squares (typical map)', persistence: 'passes seen as forest' };
// plain display names for the place picker and the "About" box (the data files keep their own technical names)
const PLACE_NAME = { spara: 'Novo Progresso, Pará (20 km test area)', rondonia: 'Rondônia (20 km)', big: 'BR-163 frontier, 60 km', frame: 'Whole radar image (~300 km)' };
const placeName = (l) => PLACE_NAME[l.id] || l.name;
function setImage(redraw = true) {
  if (state.loc) document.dispatchEvent(new CustomEvent('evidence:map-date',{detail:{date:state.loc.dates[state.i]}}));
  const loc = state.loc, op = +$('opacity').value / 100, date = loc.dates[state.i];
  if (isForestLoc()) {
    show('radar', url(state.layer, state.i), op);
    show('chg', null);
    const st = STATIC_LABEL[state.layer];
    setText($('datelabel'), st ? `${st} · ${loc.dates[0]} to ${loc.dates[loc.dates.length - 1]}` : `${date} · pass ${state.i + 1} of ${loc.dates.length}`);
    setText($('hero-what'), st ? `its ${LAYER_NAME[state.layer]} from all 9 passes` : `its forest map from ${date}`);
  } else {
    const isChg = state.layer.endsWith('chg');
    // base radar image: the chosen layer, or HV under a change layer
    show('radar', url(isChg ? 'hv' : state.layer, state.i), isChg ? 0.45 * op : op);
    const showChg = isChg && hasImage(state.layer, state.i);
    show('chg', showChg ? url(state.layer, state.i) : null, 1);
    setText($('datelabel'), `${date} · pass ${state.i + 1} of ${loc.dates.length}` + (isChg && !showChg ? ' · first pass, nothing earlier to compare with' : ''));
    setText($('hero-what'), `its ${LAYER_NAME[state.layer]} image from ${date}`);
  }
  const exploring = state.mode === 'exploring';
  $('card-radar').setAttribute('aria-current', String(exploring && !isBig() && state.layer === 'composite'));
  $('card-change').setAttribute('aria-current', String(exploring && !isBig() && state.layer === 'hvchg'));
  $('card-big').setAttribute('aria-current', String(exploring && isBig()));
  if ($('card-frame')) $('card-frame').setAttribute('aria-current', String(exploring && isFrame()));
  $('date').value = state.i;
  document.querySelectorAll('.pass').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.i === state.i)));
  const on = document.querySelector('.pass[aria-pressed=true]');
  if (on) $('rail-cursor').style.setProperty('--p', on.style.getPropertyValue('--p'));
  drawLegend();
  updateFilters();
  if (redraw) redrawLast();
}

function preload() { // so the passes and play are smooth
  if (isForestLoc()) { if (isBig()) state.loc.dates.forEach((_, i) => { const im = new Image(); im.src = url('forest', i); }); return; }
  for (const layer of ['composite', 'hv', 'hh', 'hvchg', 'hhchg'])
    state.loc.dates.forEach((_, i) => { if (hasImage(layer, i)) { const im = new Image(); im.src = url(layer, i); } });
}

// one tick per pass, placed by date; a dashed slot marks each 12-day repeat with no pass in the stack
function drawPasses() {
  const dates = state.loc.dates, t = dates.map((d) => Date.parse(d)), span = t[t.length - 1] - t[0], DAY = 864e5;
  const x = (ms) => `--p:${(((ms - t[0]) / span) * 100).toFixed(2)}`;
  let html = '<span class="rail-cursor" id="rail-cursor" aria-hidden="true"></span>';
  for (let k = 1; k < t.length; k++)
    for (let g = t[k - 1] + 12 * DAY; g < t[k] - 6 * DAY; g += 12 * DAY) html += `<span class="gap" style="${x(g)}" title="Missed pass: no radar image on this date"></span>`;
  html += dates.map((d, i) => `<button class="pass" style="${x(t[i])};--d:${i}" data-i="${i}" aria-pressed="false" aria-label="Pass ${d}" tabindex="${i === state.i ? 0 : -1}"><i></i><span>${d.slice(5)}</span></button>`).join('');
  $('passes').innerHTML = html;
  $('pass-count').textContent = String(dates.length).padStart(2, '0');
}

// strip facts and thumbnails, all from the manifest and the exported layers
function drawStrip() {
  const first = state.manifest.locations[0], fl = first.dates[first.dates.length - 1];
  // headline facts (#facts) are rendered by observatory.js from big.json / frame.json / cloud.json, independent of the map
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
  if (!state.loc || state.cinema) return; // cinema.js owns the camera during the globe fly-in
  const b = state.loc.bounds_lonlat, mob = map.getContainer().clientWidth <= 900;
  const cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padding() });
  if (!cam) return;
  // intro on a wide screen: zoom past the fit so the radar bleeds off the right edge like a photograph
  map.easeTo({ ...cam, zoom: cam.zoom + (state.mode === 'intro' && !mob && !isBig() ? 1.15 : 0), duration: reduced ? 0 : duration, easing: easeInOut });
}
function focusBounds(b) { // b = W S E N of a patch: zoom to it, clear of the panel
  map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padding(), maxZoom: 15, duration: reduced ? 0 : 1100, easing: easeInOut });
}
// ---------- a selected patch: bright outline above every layer, camera fitted to the free part of the map ----------
function featureBounds(f) { // [W, S, E, N] of any Polygon / MultiPolygon
  let w = 180, s = 90, e = -180, n = -90;
  const walk = (a) => { if (typeof a[0] === 'number') { w = Math.min(w, a[0]); e = Math.max(e, a[0]); s = Math.min(s, a[1]); n = Math.max(n, a[1]); } else a.forEach(walk); };
  walk(f.geometry.coordinates);
  return [w, s, e, n];
}
function panelInsets() { // px of the map hidden by the left rail and, if open, the investigation panel (+ 40 px breathing room)
  const cr = map.getContainer().getBoundingClientRect();
  if (cr.width <= 900) return padding(); // phones: the panel is a sheet over the map; keep the standard fit
  const dlg = $('investigation');
  const right = dlg && dlg.open ? Math.max(60, cr.right - dlg.getBoundingClientRect().left + 40) : 60;
  return { top: 90, bottom: 110, left: 76 + 40, right: Math.round(right) };
}
function ensureSelLayers() {
  if (!map.getSource('sel')) map.addSource('sel', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  if (!map.getLayer('sel-halo')) map.addLayer({ id: 'sel-halo', type: 'line', source: 'sel', layout: { 'line-join': 'round' }, paint: { 'line-color': '#000000', 'line-width': 7, 'line-opacity': 0.65 } });
  if (!map.getLayer('sel-line')) map.addLayer({ id: 'sel-line', type: 'line', source: 'sel', layout: { 'line-join': 'round' }, paint: { 'line-color': '#ffe14d', 'line-width': 3.5 } });
  map.moveLayer('sel-halo'); map.moveLayer('sel-line'); // layers added later (frame patches, 3D columns) must not cover it
}
function focusSelected(f) {
  if (!f || !f.geometry) return;
  ensureSelLayers();
  map.getSource('sel').setData({ type: 'Feature', geometry: f.geometry, properties: {} });
  const b = featureBounds(f);
  // fitBounds ignored the zoom cap here, so: zoom = fit zoom capped at 14, centre = the patch, shifted by `offset` so it sits in the middle of the free map area
  const ins = panelInsets(), cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], { padding: ins });
  map.easeTo({ center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], zoom: Math.min(cam ? cam.zoom : 14, 14), offset: [(ins.left - ins.right) / 2, (ins.top - ins.bottom) / 2], duration: reduced ? 0 : 900, easing: easeInOut });
}
function clearSelected() { if (map.getSource('sel')) map.getSource('sel').setData({ type: 'FeatureCollection', features: [] }); }
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
  } else if (target === 'frame' && state.frame) {
    if (!isFrame()) { $('loc').value = 'frame'; await selectLoc('frame'); }
  } else if (['composite', 'hv', 'hh', 'hvchg', 'hhchg'].includes(target)) {
    if (isForestLoc() && first) { $('loc').value = first.id; await selectLoc(first.id); }
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
  if (isForestLoc()) {
    const T = (isFrame() ? state.frameMeta : state.bigMeta).T_db.toFixed(2);
    const fnf = `<span class="sw" style="background:#2f6b4f"></span> forest (tree signal &ge; ${T} dB) <span class="sw" style="background:#b4401c;margin-left:6px"></span> open land`;
    let body = `${fnf}. No colour = outside the strip the satellite sees ${Glossary.tip('swath')} on at least one pass. 100 m squares.`;
    if (L === 'confidence') {
      const c = state.bigMeta.confidence || {};
      body = `${fnf} <span class="sw" style="background:#8a9490;margin-left:6px"></span> unsure: the typical tree signal is within &plusmn;${c.uncertain_band_db} dB of the cut-off (${pct(c.share && c.share.uncertain)} of mapped squares). We picked this range for display. We didn't tune it.`;
    } else if (L === 'persistence') {
      const pc = state.bigMeta.persistence || {}, cols = pc.colors || {};
      body = `<span class="ramp">${Object.keys(cols).map((k) => `<span class="sw" style="background:${cols[k]}" title="${k} of 9"></span>`).join('')}</span> 0 &rarr; 9 of the 9 passes looked like forest. ${pct(pc.blocks && pc.blocks.share && pc.blocks.share['9'])} of squares were forest on every pass, ${pct(pc.blocks && pc.blocks.share && pc.blocks.share['0'])} on none.`;
    }
    el.innerHTML = `<div class="note keyrow" style="padding-left:0">${body}</div>`;
    return;
  }
  const bar = (css, lo, hi, unit) => `<div class="legend" style="background:${css}"></div><div class="legend-lab"><span>${lo}</span><span>${hi}</span></div><div class="note">${unit}</div>`;
  if (L === 'hv' || L === 'hh') el.innerHTML = bar('linear-gradient(90deg,#000,#fff)', `${s[L].lo} dB`, `${s[L].hi} dB`, `${L === 'hv' ? 'Tree' : 'Ground'} signal (${L.toUpperCase()}), radar echo brightness ${Glossary.tip('gamma0')}. One fixed brightness range for all dates ${Glossary.tip('stretch')}: values beyond it look the same as the edge.`);
  else if (L.endsWith('chg')) el.innerHTML = bar('linear-gradient(90deg,#00f,#fff,#f00)', `-${state.manifest.change_range_db} dB (drop)`, `+${state.manifest.change_range_db} dB (rise)`, `This date minus the average of all earlier dates, in ~80 m squares. Changes under 1 dB are left clear, because radar grain ${Glossary.tip('speckle')} on a single date is ~0.4 dB at 20 m. It's a preview made from the display images, which are cut off at the brightness range. So real drops can be bigger.`);
  else el.innerHTML = `<div class="note">Red = ground signal, HH (${s.hh.lo} to ${s.hh.hi} dB). Green = tree signal, HV (${s.hv.lo} to ${s.hv.hi} dB). Blue = the difference, HH&minus;HV (${s.ratio.lo} to ${s.ratio.hi} dB). Green/yellow = forest, purple/blue = cleared or bare.</div>`;
}

// ---------- time series ----------
async function loadSeries() {
  const loc = state.loc;
  state.series = null;
  if (loc.kind === 'big' || loc.kind === 'frame') return; // no per-pixel series file for the forest maps; lost patches carry their own
  try {
    const r = await fetch(`${DATA}${loc.id}/series.bin`);
    if (!r.ok) throw new Error('Series unavailable');
    const bytes = new Uint8Array(await r.arrayBuffer());
    if (bytes.length !== loc.series_shape.reduce((a, b) => a * b, 1)) throw new Error('Invalid series size');
    if (state.loc === loc) state.series = bytes;
  } catch {
    if (state.loc === loc) $('chart').textContent = 'The history of single spots isn\'t available. You can still click a detection patch.';
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
  return `<svg class="${fresh ? 'fresh' : ''}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ground signal (HH) and tree signal (HV) over time at the selected spot">${grid}${ticks}${cur}
    ${line(ref.hh, CHART.hh, true)}${line(ref.hv, CHART.hv, true)}${line(v.hh, CHART.hh)}${line(v.hv, CHART.hv)}${dots(v.hh, CHART.hh)}${dots(v.hv, CHART.hv)}</svg>`;
}
function placeMarker(lon, lat, fresh) {
  if (state.marker) state.marker.setLngLat([lon, lat]);
  else {
    const el = document.createElement('div');
    el.className = 'pin';
    el.setAttribute('aria-label', 'Selected spot');
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

const KEY = `<b style="color:${CHART.hh}">ground signal (HH)</b> and <b style="color:${CHART.hv}">tree signal (HV)</b>`;
function drawChart(lon, lat, fresh = true) {
  state.last = { kind: 'point', lon, lat };
  if (isForestLoc()) { $('chart').innerHTML = `<div class="hint">Click a ${isFrame() ? 'magenta' : 'red'} possible clearing. You'll see its tree signal over time, next to the forest cut-off.</div>`; return; }
  const c = cellAt(lon, lat), el = $('chart');
  if (!c) { el.innerHTML = '<div class="hint">This spot is outside the radar image. Click inside it.</div>'; return; }
  if (!state.series) { el.textContent = 'No signal history here. Try a detection patch, or reload the page.'; return; }
  const v = valuesAt(...c), ref = state.loc.stable_forest_ref;
  if (!v.hv.some(Boolean)) { el.innerHTML = '<div class="hint">No radar data at this spot.</div>'; return; }
  const clippedAny = [...v.hh, ...v.hv].some((p) => p && p.clipped);
  el.innerHTML = `${chartSVG(v, ref, state.loc.dates, fresh)}
    <div class="note">${KEY} (dB) at ${lat.toFixed(4)}, ${lon.toFixed(4)}, in a ~80 m square. Dashed = forest that didn't change ${Glossary.tip('stable')} (middle value of ${ref.n_pixels.toLocaleString()} px with tree signal &ge; ${state.manifest.t_db_forest.toFixed(2)} dB on every date). Clearing usually shows as the tree signal falling away from the dashed line.</div>
    ${clippedAny ? `<div class="warn">Hollow dots hit the edge of the brightness range ${Glossary.tip('stretch')}. The true value is at or beyond it.</div>` : ''}`;
  placeMarker(lon, lat, fresh);
}

// A clicked detection: the series are patch means of the 5x5-multilooked full-precision stack (detections.geojson).
const SPLIT_NAME = { tune: 'in the half we tuned on', holdout: 'in the test half, never used for tuning', buffer: 'in the gap strip between the halves' };
const STAGE_NAME = { early: 'early sign: ground signal goes up', late: 'later sign: tree signal goes down' };
function drawDetection(f, lngLat, fresh = true) {
  if (fresh) document.dispatchEvent(new CustomEvent('evidence:selection',{detail:{feature:f,kind:'det',point:[lngLat.lng,lngLat.lat],dates:state.loc.dates}}));
  state.last = { kind: 'det', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates;
  const title = `Radar detection ${esc(p.id)}: ${esc(p.area_ha)} ha, first seen ${esc(p.first_date)}, ${esc(SPLIT_NAME[p.split] || p.split)}`;
  const series = (a) => (Array.isArray(a) && a.length === dates.length ? a.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null);
  const hh = series(p.hh_series_db), hv = series(p.hv_series_db);
  if (!hh || !hv) {
    el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Can't draw the chart: each signal needs ${dates.length} values, one per date.</div>`;
    return;
  }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh, hv }, state.loc.stable_forest_ref, dates, fresh)}
    <div class="note">${KEY} (dB): average over this patch from the full-detail data (5&times;5 pixels averaged to cut radar grain ${Glossary.tip('speckle')}). Stage: ${esc(STAGE_NAME[p.stage] || p.stage)}. Dashed = forest that didn't change, from the display images (middle value of ${state.loc.stable_forest_ref.n_pixels.toLocaleString()} px), for scale only. Our photo check can't tell if this patch is clearing or radar noise. Someone independent needs to review it.</div>`;
  placeMarker(lngLat.lng, lngLat.lat, fresh);
}
// A clicked lost patch on the 60 km map: patch-mean HV from the stack (lost.geojson hv_series_db) vs the fixed threshold.
function drawLost(f, lngLat, fresh = true) {
  if (fresh) document.dispatchEvent(new CustomEvent('evidence:selection',{detail:{feature:f,kind:'lost',point:[lngLat.lng,lngLat.lat],dates:state.loc.dates}}));
  state.last = { kind: 'lost', id: f.properties.id, lon: lngLat.lng, lat: lngLat.lat };
  const p = f.properties, el = $('chart'), dates = state.loc.dates, T = (isFrame() ? state.frameMeta : state.bigMeta).T_db;
  const cat = { alert_supported: 'matches an alert (a GLAD alert in the patch)', radar_only_unconfirmed: 'radar only, not confirmed' }[p.category];
  const title = `Possible clearing ${esc(p.id)}: ${esc(p.area_ha)} ha, open land from ${esc(p.first_switch_date || p.first_flagged || 'n/a')}${cat ? `, ${cat}` : ''}${p.in_original_window ? ', inside the test area' : ''}`;
  const hv = Array.isArray(p.hv_series_db) && p.hv_series_db.length === dates.length ? p.hv_series_db.map((x) => (Number.isFinite(x) ? { db: x, clipped: false } : null)) : null;
  if (!hv) { el.innerHTML = `<div class="ctitle">${title}</div><div class="warn">Can't draw the chart: the tree signal needs ${dates.length} values, one per date.</div>`; return; }
  el.innerHTML = `<div class="ctitle">${title}</div>${chartSVG({ hh: dates.map(() => null), hv }, { hh: [], hv: dates.map(() => T) }, dates, fresh)}
    <div class="note"><b style="color:${CHART.hv}">Tree signal (HV)</b> (dB): average over this patch's 100 m squares, from the full-detail data. Dashed = the fixed forest cut-off ${T.toFixed(2)} dB (above = forest). Wet ground or radar grain ${Glossary.tip('speckle')} can also push it below the line. ${p.n_blocks === 1 ? 'This is a single 1 ha square, and it is ' : 'It is '}not confirmed.</div>`;
  placeMarker(lngLat.lng, lngLat.lat, fresh);
}
function redrawLast() { // same selection, new pass: redraw without the entrance animation
  const l = state.last;
  if (!l) return;
  if (l.kind === 'lost') {
    const ls = lostSet(), f = ls && ls.byId.get(l.id);
    if (f) drawLost(f, { lng: l.lon, lat: l.lat }, false);
    return;
  }
  if (l.kind === 'det') {
    const f = state.det && state.det.byId.get(l.id);
    if (f) drawDetection(f, { lng: l.lon, lat: l.lat }, false);
  } else drawChart(l.lon, l.lat, false);
}

// ---------- story: rendered by observatory.js (#story), so it does not wait for the map's load event ----------

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
  lg.replaceChildren(document.createTextNode('no colour = no loss in 2021–2025:'));
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

// #results (the failed 1 dB detector) is rendered by observatory.js from data/metrics.json

async function loadExtras() {
  // start every fetch at once, add the layers in drawing order (Hansen under alerts under detections)
  const pHan = getJSON(`${DATA}spara/hansen_loss.json`);
  const pDet = getJSON('data/detections.geojson'), pMet = getJSON('data/metrics.json');
  const han = await pHan;
  if (han && han.years && state.manifest.locations.some((l) => l.id === 'spara') && await fileExists(`${DATA}spara/hansen_loss.webp`)) addHansen(han);
  else pending('han', true);
  pending('ref', false); // enabled now; the file itself is fetched on first toggle (ensureRef), and addRef shows pending if it fails
  addDetections(await pDet);
  state.metrics = await pMet;
}

let refLoading = null;
function ensureRef() { // reference_alerts.geojson (1.6 MB) is fetched the first time the GLAD-L toggle is switched on
  if (!refLoading) refLoading = getJSON('data/reference_alerts.geojson').then((fc) => { addRef(fc); updateFilters(); applyVisibility(); });
  return refLoading;
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
  if (map.getLayer('lost-img') && state.bigMeta && state.bigMeta.first_switch) {
    const want = `${BIG}${$('t-fs').checked ? state.bigMeta.first_switch.file : state.bigMeta.layers.lost}`;
    if (state.lostImgHref !== want) { state.lostImgHref = want; map.getSource('lost-img').updateImage({ url: want, coordinates: corners(state.bigMeta.bounds_lonlat) }); }
  }
  const frame = isFrame();
  const fvis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on && ex && frame ? 'visible' : 'none'); };
  fvis('flost-img', $('t-flost').checked && !$('t-ffs').checked);
  fvis('ffs-img', $('t-flost').checked && $('t-ffs').checked);
  fvis('flost-fill', $('t-flost').checked);
  fvis('flost-line', $('t-flost').checked);
  fvis('fout-line', $('t-fout').checked);
  fvis('fout-label', $('t-fout').checked);
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
    ['How often our typical forest map agrees with Hansen', `${pct(fm.oa)} vs ${pct(fm.all_forest_baseline)} if you just guessed "forest" everywhere`, 'agreement', 'baseline'],
    ['Agreement score without lucky guesses', typeof fm.kappa === 'number' ? fm.kappa.toFixed(3) : 'not available', 'kappa'],
    ['Squares scored (test area left out)', `${int(bl.scored)} × 1 ha`, 'block'],
    ['Squares marked as possible clearing (not confirmed)', `${int(lr.lost_blocks)} (${int(lr.lost_ha)} ha)`, 'flag'],
  ];
  for (const [src, label] of [['GLAD-L', 'GLAD-L'], ['GLAD-S2', 'GLAD-S2']]) {
    const a = al[src];
    rows.push([`Possible clearings with a ${label} alert`, a ? `${pct(a.lost.precision_like)} vs ${pct(a.control.precision_like, 2)} for random forest that didn't change` : 'not available', 'precision']);
  }
  box.append(kvList(rows));
  const w = sc.alert_windows || {};
  box.append(mk('p', 'Nobody has confirmed these possible clearings. The rule compares the last two passes, late in the dry season. So some flags are likely seasonal drying. What counts is how they compare with random forest that didn\'t change. Don\'t read the flagged area as forest loss.', 'note'));
  const pre = mk('p', `Alerts dated ${w.precision ? w.precision.join(' to ') : 'n/a'} (±24 days around ${w.reference ? w.reference.join(' to ') : 'n/a'}). We scored this once, with the rules written down first `, 'note');
  pre.append(Glossary.tipEl('prereg'), document.createTextNode(' (validation/PREREG_scale.md). Full numbers: validation/scale_metrics.json.'));
  box.append(pre);
}

function renderBigProtected(pj) {
  const box = $('big-protected');
  box.replaceChildren();
  if (!pj || !Array.isArray(pj.areas)) { box.append(mk('span', 'not available', 'tag')); return; }
  const dl = mk('dl', undefined, 'kv');
  pj.areas.forEach((a) => dl.append(mk('dt', `${a.name} (${a.kind.split(' (')[0]})`),
    mk('dd', `${int(a.lost_blocks_inside)} squares · ${a.lost_ha_inside} ha (${pct(a.lost_share_of_valid_blocks)} of its mapped squares)`)));
  const o = pj.outside_all_areas || {};
  dl.append(mk('dt', 'Outside all protected areas'), mk('dd', `${int(o.lost_blocks)} squares (${pct(o.lost_share_of_valid_blocks)} of mapped squares)`));
  box.append(dl);
  box.append(mk('p', `Whole 60 km map, test area included (${int(pj.total_lost_blocks)} squares marked as possible clearing, not confirmed). A square counts when its centre is inside the official boundary. Boundaries: FUNAI Terras Indígenas (read 2026-11-14). MMA CNUC 07/2026 has no conservation area here. See submission/sources.md.`, 'note'));
}

function watchlist() {
  return state.lost.features.map((f) => ({ id: f.properties.id, centroid_lon: f.properties.centroid_lon, centroid_lat: f.properties.centroid_lat,
    area_ha: f.properties.area_ha, first_flagged: f.properties.first_flagged, category: f.properties.category ?? null }));
}
function saveFile(name, text, type) {
  const a = document.createElement('a'), u = URL.createObjectURL(new Blob([text], { type }));
  a.href = u; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 1000);
}
function downloadWatchlist(kind) {
  const rows = watchlist();
  if (kind === 'geojson') {
    const fc = { type: 'FeatureCollection', name: 'br163_60km_forest_lost_watchlist',
      description: `Flagged patches (class-switch rule, ${state.loc.dates[0]}..${state.loc.dates[state.loc.dates.length - 1]}), NISAR HV threshold ${state.bigMeta.T_db.toFixed(2)} dB. first_flagged: ${state.bigMeta.first_flagged_definition}. Unverified radar flags, not confirmed clearing.`,
      features: rows.map((r) => ({ type: 'Feature', properties: r, geometry: { type: 'Point', coordinates: [r.centroid_lon, r.centroid_lat] } })) };
    saveFile('br163_forest_lost_watchlist.geojson', JSON.stringify(fc), 'application/geo+json');
  } else {
    const head = ['id', 'centroid_lon', 'centroid_lat', 'area_ha', 'first_flagged', 'category'];
    saveFile('br163_forest_lost_watchlist.csv', [head.join(','), ...rows.map((r) => head.map((k) => r[k] ?? '').join(','))].join('\n') + '\n', 'text/csv');
  }
}

async function loadBig() {
  const [meta, lost, prot, pj] = await Promise.all([getJSON(`${BIG}big.json`), getJSON(`${BIG}lost.geojson`), getJSON(`${BIG}protected.geojson`), getJSON(`${BIG}big_protected.json`)]);
  if (!meta || !Array.isArray(meta.dates) || !Array.isArray(meta.bounds_lonlat)) return;
  state.bigMeta = meta;
  state.big = { id: 'big', kind: 'big', name: 'BR-163 frontier, 60 km (forest map)', dates: meta.dates, bounds_lonlat: meta.bounds_lonlat,
    notes: 'Forest / non-forest from one fixed NISAR HV threshold on every pass (track 2, frame 174, ascending), 100 m blocks; the swath edge cuts the west of the box. Out-of-sample: threshold fixed on a 10 km strip, tested here unchanged. Agreement with Hansen/GLAD, a reference, not ground truth.' };
  $('loc').append(new Option(placeName(state.big), 'big'));
  const c = corners(meta.bounds_lonlat);
  map.addSource('lost-img', { type: 'image', url: `${BIG}${meta.layers.lost}`, coordinates: c });
  map.addLayer({ id: 'lost-img', type: 'raster', source: 'lost-img', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  if (lost && Array.isArray(lost.features)) {
    const feats = lost.features.filter((f) => f && f.geometry && f.properties && Number.isInteger(f.properties.id));
    state.lost = { features: feats, byId: new Map(feats.map((f) => [f.properties.id, f])) };
    map.addSource('lostp', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    map.addLayer({ id: 'lost-fill', type: 'fill', source: 'lostp', layout: { visibility: 'none' }, paint: { 'fill-color': '#b4401c', 'fill-opacity': 0.01 } });
    map.addLayer({ id: 'lost-line', type: 'line', source: 'lostp', layout: { visibility: 'none' }, minzoom: 12, paint: { 'line-color': ['match', ['get', 'category'], 'alert_supported', '#fdd663', '#f3b49b'], 'line-width': ['match', ['get', 'category'], 'alert_supported', 1.6, 0.8] } });
    $('dl-geojson').disabled = false; $('dl-csv').disabled = false;
    $('dl-note').textContent = `${feats.length.toLocaleString()} patches. Each row has: id, centre lon/lat, area_ha, first_flagged (${meta.first_flagged_definition}). These are radar flags only, not confirmed.`;
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
  map.addSource('win-pt', { type: 'geojson', data: { type: 'Feature', properties: { t: 'test area, left out of the bigger scores' }, geometry: { type: 'Point', coordinates: [(b[0] + b[2]) / 2, b[3]] } } });
  map.addLayer({ id: 'win-label', type: 'symbol', source: 'win-pt', layout: { visibility: 'none', 'text-field': ['get', 't'], 'text-size': 12, 'text-anchor': 'bottom', 'text-offset': [0, -0.3], 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#fdd663', 'text-halo-color': '#091008', 'text-halo-width': 1.5 } });
  renderBigResults(meta);
  renderBigProtected(pj);
  if (meta.first_switch) legendRow($('fs-legend'), Object.entries(meta.first_switch.legend).map(([d, col]) => [col, d.slice(5)]));
  renderBigExtras(meta, await getJSON(`${BIG}cloud.json`));
  $('dl-geojson').onclick = () => downloadWatchlist('geojson');
  $('dl-csv').onclick = () => downloadWatchlist('csv');
}

// ---------- 60 km map: credibility pack (big.json) and optical-vs-radar timeline (cloud.json); numbers read from the files ----------
function kvList(rows) { // rows: [label, value, tip key(s) for the label?, tip key(s) for the value?]
  const dl = mk('dl', undefined, 'kv');
  const withTips = (n, keys) => { [].concat(keys || []).forEach((k) => { n.append(' ', Glossary.tipEl(k)); }); return n; };
  rows.forEach(([k, v, tk, tv]) => dl.append(withTips(mk('dt', k), tk), withTips(mk('dd', v), tv)));
  return dl;
}
function renderBigExtras(meta, cloud) {
  const cm = meta.class_metrics && meta.class_metrics.median;
  const cls = $('big-classes'); cls.replaceChildren();
  if (cm) {
    const c = cm.confusion;
    const cnote = mk('p', 'Hansen is another map to compare with, not the final word. ', 'note');
    cnote.append(mk('small', `Details: ${meta.class_metrics.scope}. ${meta.class_metrics.reference}.`));
    cls.append(kvList([
      ['Forest: how often Hansen agrees / how much we found', `${pct(cm.forest_precision)} / ${pct(cm.forest_recall)}`, ['precision', 'recall']],
      ['Open land: how often Hansen agrees / how much we found', `${pct(cm.nonforest_precision)} / ${pct(cm.nonforest_recall)}`],
      ['We say forest: Hansen says forest / open land', `${int(c.map_forest.hansen_forest)} / ${int(c.map_forest.hansen_nonforest)} squares`],
      ['We say open land: Hansen says forest / open land', `${int(c.map_nonforest.hansen_forest)} / ${int(c.map_nonforest.hansen_nonforest)} squares`],
    ]), cnote);
  } else cls.append(mk('span', 'not available', 'tag'));

  const lc = meta.lost_categories, cats = $('big-cats'); cats.replaceChildren();
  if (lc && lc.patches) {
    const a = lc.patches.alert_supported, r = lc.patches.radar_only_unconfirmed;
    cats.append(kvList([
      ['Matches an alert (GLAD-L or GLAD-S2 in the patch)', `${int(a.patches)} patches · ${int(a.ha)} ha`, 'alertsupported'],
      ['Radar only, not confirmed', `${int(r.patches)} patches · ${int(r.ha)} ha`, 'radaronly'],
    ]), mk('p', 'Radar-only patches are radar changes that nobody has confirmed. They aren\'t deforestation. Alerts are dated 2026-06-26 to 2026-11-05, over the whole 60 km map, test area included.', 'note'));
  } else cats.append(mk('span', 'not available', 'tag'));

  const wp = meta.watch_priorities, list = $('big-watch'); list.replaceChildren();
  if (wp && Array.isArray(wp.items)) {
    $('big-watch-note').textContent = 'The 20 biggest possible clearings. Distance is to land that was already open at the start (100 m means touching). Check these first, but none is confirmed clearing. Click one to fly to it.';
    wp.items.forEach((it) => {
      const li = mk('li'), b = mk('button', undefined, 'watch-item'); b.type = 'button';
      b.append(mk('b', `${it.area_ha} ha`), mk('span', `${it.category === 'alert_supported' ? 'matches an alert' : 'radar only'} · from ${it.first_switch_date} · ${int(it.distance_m)} m from cleared land${it.in_original_window ? ' · test area' : ''}`));
      b.onclick = () => openLost(it.id);
      li.append(b); list.append(li);
    });
  }
  renderCloud(cloud);
}
async function openLost(id) {
  if (!isBig()) { $('loc').value = 'big'; await selectLoc('big'); }
  setMode('exploring');
  const f = state.lost && state.lost.byId.get(id);
  if (!f) return;
  const p = f.properties, d = 0.006;
  focusBounds([p.centroid_lon - d, p.centroid_lat - d, p.centroid_lon + d, p.centroid_lat + d]);
  drawLost(f, { lng: p.centroid_lon, lat: p.centroid_lat });
}
function renderCloud(c) {
  const box = $('big-cloud'); box.replaceChildren();
  if (!c || !Array.isArray(c.scenes) || !c.scenes.length) { box.append(mk('span', 'not available', 'tag')); return; }
  const passes = c.nisar_passes, good = c.good_threshold, W = 340, H = 150, ml = 30, mr = 8, mt = 22, mb = 22;
  const t0 = Date.parse(passes[0]), t1 = Date.parse(passes[passes.length - 1]);
  const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr), Y = (f) => mt + (1 - f) * (H - mt - mb);
  let g = '';
  for (const f of [0, 0.5, 1]) g += `<line x1="${ml}" x2="${W - mr}" y1="${Y(f)}" y2="${Y(f)}" stroke="${CHART.grid}" stroke-opacity=".5"/><text x="${ml - 4}" y="${Y(f) + 4}" fill="${CHART.text}" font-size="10" text-anchor="end">${f * 100}%</text>`;
  g += `<line x1="${ml}" x2="${W - mr}" y1="${Y(good)}" y2="${Y(good)}" stroke="#fdd663" stroke-dasharray="3 3" stroke-opacity=".8"/>`;
  g += passes.map((d) => `<line x1="${X(d)}" x2="${X(d)}" y1="4" y2="14" stroke="${CHART.hv}" stroke-width="2"/>`).join('');
  g += c.scenes.map((sc) => { const f = sc.clear_fraction_aoi; return `<circle cx="${X(sc.date)}" cy="${Y(f)}" r="3.2" fill="${f >= good ? '#CED9DF' : '#5d6b62'}"><title>${sc.date}: ${(100 * f).toFixed(1)}% clear</title></circle>`; }).join('');
  g += [0, 3, 6, 8].map((i) => `<text x="${X(passes[i])}" y="${H - 6}" fill="${CHART.text}" font-size="10" text-anchor="${i === 8 ? 'end' : 'middle'}">${passes[i].slice(5)}</text>`).join('');
  const svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cloud-free share of each Sentinel-2 photo, and the NISAR pass dates">${g}</svg>`;
  const s = c.summary && c.summary.aoi;
  const gaps = passes.slice(1).map((d, i) => (Date.parse(d) - Date.parse(passes[i])) / 864e5);
  const wrap = mk('div'); wrap.innerHTML = svg; box.append(wrap);
  const tnote = mk('p', `Ticks on top: the 9 NISAR passes, all usable. Its long-wave radar passes through clouds `, 'note');
  tnote.append(Glossary.tipEl('lband'), document.createTextNode(` (longest gap ${Math.max(...gaps)} days). Dots: Sentinel-2 photos `), Glossary.tipEl('sentinel2'),
    document.createTextNode(`, with the share of the 60 km box that was cloud-free `), Glossary.tipEl('scene'), document.createTextNode(`. Light = at least ${good * 100}% clear.`));
  box.append(tnote);
  if (s) box.append(kvList([
    ['Sentinel-2 photos, 06-26 to 10-12', `${int(s.n_scenes)}, of which ${int(s.n_ge_80pct_clear)} at least 80% clear`],
    ['Typical cloud-free share per photo', pct(s.median_clear_fraction)],
    ['Longest gap between clear Sentinel-2 views', `${s.longest_gap_days_between_good_views} days`],
  ]));
  box.append(mk('p', 'This is the dry season, and Sentinel-2 actually saw this area well from June to October. Cloud didn\'t blind it. What NISAR adds here: every pass is usable without checking for cloud. Cloud starts building in September. We didn\'t measure the wet season (about November to May). Sentinel-2\'s cloud check misses haze and small clouds, so the clear shares are upper limits. validation/cloud_blindness.json.', 'note'));
}

// ---------- full NISAR frame (web/data/explore/frame/, frame.json + layers; scores copied there from validation/frame_metrics.json) ----------
const FRAME = `${DATA}frame/`;
function legendRow(el, items) {
  el.replaceChildren();
  items.forEach(([col, label]) => { const sw = mk('span', undefined, 'sw'); sw.style.background = col; sw.style.marginLeft = '6px'; el.append(sw, document.createTextNode(label)); });
}
async function loadFrame() {
  const meta = await getJSON(`${FRAME}frame.json`);
  if (!meta || !Array.isArray(meta.dates) || !Array.isArray(meta.bounds_lonlat_wsen)) return;
  state.frameMeta = meta;
  const b = meta.bounds_lonlat_wsen, c = corners(b);
  state.frame = { id: 'frame', kind: 'frame', name: `Full NISAR frame${Number.isFinite(meta.scores?.blocks?.scored_km2) ? `, ${Math.round(meta.scores.blocks.scored_km2).toLocaleString()} km² scored` : ''} (forest map)`, dates: meta.dates, bounds_lonlat: b,
    notes: 'The whole radar frame (track 2, frame 174, ascending), 100 m blocks, the same fixed HV threshold and forest-to-non-forest flag rule as the 60 km map. Only the 9-pass median map is shown at this size. Out-of-sample; agreement with Hansen/GLAD is a reference, not ground truth.' };
  $('loc').append(new Option(placeName(state.frame), 'frame'));
  const raster = { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' };
  map.addSource('flost-img', { type: 'image', url: `${FRAME}${meta.layers.lost}`, coordinates: c });
  map.addLayer({ id: 'flost-img', type: 'raster', source: 'flost-img', layout: { visibility: 'none' }, paint: raster });
  map.addSource('ffs-img', { type: 'image', url: `${FRAME}${meta.layers.first_switch}`, coordinates: c });
  map.addLayer({ id: 'ffs-img', type: 'raster', source: 'ffs-img', layout: { visibility: 'none' }, paint: raster });
  const outl = { type: 'FeatureCollection', features: Object.entries(meta.outlines || {}).map(([k, g]) => ({ type: 'Feature', properties: { name: k === 'window_20km' ? 'test area' : '60 km map' }, geometry: g })) };
  map.addSource('fout', { type: 'geojson', data: outl });
  map.addLayer({ id: 'fout-line', type: 'line', source: 'fout', layout: { visibility: 'none' }, paint: { 'line-color': '#fdd663', 'line-width': 1.4, 'line-dasharray': [3, 2] } });
  const pts = { type: 'FeatureCollection', features: outl.features.map((f) => { const r = f.geometry.coordinates[0]; return { type: 'Feature', properties: f.properties, geometry: { type: 'Point', coordinates: [Math.min(...r.map((q) => q[0])), Math.max(...r.map((q) => q[1]))] } }; }) };
  map.addSource('fout-pt', { type: 'geojson', data: pts });
  map.addLayer({ id: 'fout-label', type: 'symbol', source: 'fout-pt', layout: { visibility: 'none', 'text-field': ['get', 'name'], 'text-size': 11, 'text-anchor': 'bottom-left', 'text-font': ['Noto Sans Regular'] }, paint: { 'text-color': '#fdd663', 'text-halo-color': '#091008', 'text-halo-width': 1.5 } });
  legendRow($('ffs-legend'), (meta.first_switch_legend || []).map((l) => [l.colour, l.date.slice(5)]));
  renderFrameResults(meta);
  if ($('card-frame')) {
    $('thumb-frame').src = `${FRAME}${meta.layers.median}`; $('card-frame').hidden = false;
    if (Number.isFinite(meta.scores?.blocks?.scored_km2)) $('card-frame-sub').textContent = `${Math.round(meta.scores.blocks.scored_km2).toLocaleString()} km² scored`;
    if (Number.isFinite(meta.counts?.geojson_min_area_ha_applied)) $('frame-min-ha').textContent = String(meta.counts.geojson_min_area_ha_applied);
  }
}
let frameLostLoading = null;
function loadFrameLost() { // 9 MB of patches: fetched only when the frame is opened
  if (frameLostLoading) return frameLostLoading;
  frameLostLoading = (async () => {
    const gj = await getJSON(`${FRAME}${state.frameMeta.layers.lost_patches}`);
    if (!gj || !Array.isArray(gj.features)) return;
    const feats = gj.features.filter((f) => f && f.geometry && f.properties && Number.isInteger(f.properties.id));
    state.frameLost = { features: feats, byId: new Map(feats.map((f) => [f.properties.id, f])) };
    map.addSource('flostp', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    map.addLayer({ id: 'flost-fill', type: 'fill', source: 'flostp', layout: { visibility: 'none' }, paint: { 'fill-color': '#ff2bd6', 'fill-opacity': 0.01 } });
    map.addLayer({ id: 'flost-line', type: 'line', source: 'flostp', layout: { visibility: 'none' }, minzoom: 11, paint: { 'line-color': ['match', ['get', 'category'], 'alert_supported', '#fdd663', '#ffb3ef'], 'line-width': 0.8 } });
    applyVisibility();
  })();
  return frameLostLoading;
}
function renderFrameResults(meta) {
  const box = $('frame-results'), sc = meta.scores || {};
  box.replaceChildren();
  const fm = (sc.a_forest_map || {}).median || {}, bl = sc.blocks || {}, lr = sc.loss_rule || {}, al = sc.b_alerts || {};
  const rows = [
    ['Area scored (60 km map and test area left out)', `${int(bl.scored)} squares · ${typeof bl.scored_km2 === 'number' ? Math.round(bl.scored_km2).toLocaleString() : 'n/a'} km²`, 'block'],
    ['How often our typical forest map agrees with Hansen', `${pct(fm.oa)} vs ${pct(fm.all_forest_baseline)} if you just guessed "forest" everywhere`, 'agreement', 'baseline'],
    ['Agreement score without lucky guesses', typeof fm.kappa === 'number' ? fm.kappa.toFixed(3) : 'not available', 'kappa'],
    ['Forest: how often Hansen agrees / how much we found', `${pct(fm.forest_precision)} / ${pct(fm.forest_recall)}`, ['precision', 'recall']],
    ['Open land: how often Hansen agrees / how much we found', `${pct(fm.nonforest_precision)} / ${pct(fm.nonforest_recall)}`],
    ['Squares marked as possible clearing (not confirmed)', `${int(lr.lost_blocks)} (${int(lr.lost_ha)} ha)`, 'flag'],
  ];
  for (const src of ['GLAD-L', 'GLAD-S2']) {
    const a = al[src];
    if (a) rows.push([`Possible clearings with a ${src} alert`, `${pct(a.lost.precision_like)} vs ${pct(a.control.precision_like, 2)} for random forest that didn't change`, 'precision']);
  }
  box.append(kvList(rows));
  const n = meta.counts || {}, pg = n.patches_in_geojson || {};
  $('frame-note').textContent = `The map shows ${int(pg.patches)} possible clearings of at least ${n.geojson_min_area_ha_applied} ha (${int(pg.alert_supported)} match an alert, ${int(pg.radar_only_unconfirmed)} radar only). Smaller patches are in the image, but you can't click them. Full numbers: validation/frame_metrics.json and results_final.md "Forest map, full frame".`;
  const pd = (sc.a_forest_map || {}).per_date || {}, ds = Object.keys(pd).sort();
  if (ds.length >= 2 && typeof pd[ds[0]].oa === 'number' && typeof pd[ds[ds.length - 1]].oa === 'number') {
    $('frame-note').textContent += ` Caution: on a single pass, agreement with Hansen falls from ${pct(pd[ds[0]].oa)} on ${ds[0]} to ${pct(pd[ds[ds.length - 1]].oa)} on ${ds[ds.length - 1]} (just guessing "forest" everywhere: ${pct(fm.all_forest_baseline)}). The tree signal drops as the dry season goes on. The rule compares the last two passes, so many flags are likely seasonal drying, not clearing. Possible clearings are about ${typeof (al['GLAD-L'] || {}).lost === 'object' && al['GLAD-L'].control.precision_like > 0 ? (al['GLAD-L'].lost.precision_like / al['GLAD-L'].control.precision_like).toFixed(1) : 'n/a'}× more likely than random forest that didn't change to overlap a GLAD-L alert. This is not accuracy, and most of them are not confirmed. Don't read the flagged area as forest loss.`;
  }
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
// "About these layers": a short plain sentence, then the technical note from the data file as small print (unchanged)
function renderAbout(loc, forest) {
  const n = loc.dates.length, span = `${loc.dates[0]} to ${loc.dates[n - 1]}`;
  const plain = {
    spara: `The 20 km area where we built and tuned the method. You see NISAR's early-release radar images, ${n} passes from ${span}.`,
    rondonia: `Our first test area. Only ${n} passes (${span}) can be used here. Alerts showed no clearing of 1 ha or more there from 2026-08-29 to 2026-10-16, so we moved to Novo Progresso.`,
    big: `A 60 km area along the BR-163 highway. On every pass, each 100 m square is called forest or open land with one fixed cut-off. The west edge is outside the satellite's strip.`,
    frame: `The whole area of one radar image, about 300 km across. It uses the same cut-off and rule as the 60 km map. At this size we only show the typical forest map.`,
  }[loc.id] || '';
  const el = $('about');
  el.replaceChildren(document.createTextNode(`${placeName(loc)}. ${plain} `));
  if (loc.id === 'spara' || loc.id === 'rondonia') el.append(Glossary.tipEl('gcov'), document.createTextNode(' '));
  el.append(mk('small', `Technical note: ${loc.notes}${forest ? '' : ' Change previews and time series are computed from these display layers (web/tools/make_explore.py), not from detect.py.'}`));
}
async function selectLoc(id) {
  stopPlay();
  state.loc = findLoc(id);
  const selected = state.loc;
  if (state.marker) { state.marker.remove(); state.marker = null; }
  state.i = state.loc.dates.length - 1;
  state.last = null;
  slots.radar.href = slots.chg.href = null;
  const sp = state.loc.id === 'spara', big = isBig(), frame = isFrame(), forest = big || frame;
  $('extras').hidden = !sp; $('extras-off').hidden = sp || forest; $('big-extras').hidden = !big; $('frame-extras').hidden = !frame;
  $('radar-layers').hidden = forest; $('big-layers').hidden = !forest; $('big-panel').hidden = !big; $('frame-panel').hidden = !frame;
  const allowed = forest ? LAYERS_FOR[state.loc.kind] : null;
  document.querySelectorAll('#big-layers input[name=layer]').forEach((r) => { r.closest('label').hidden = !!allowed && !allowed.includes(r.value); });
  state.layer = forest ? allowed[0] : (['forest', 'median', 'confidence', 'persistence'].includes(state.layer) ? 'hv' : state.layer);
  if (frame) loadFrameLost();
  document.querySelectorAll('input[name=layer]').forEach((r) => { r.checked = r.value === state.layer; });
  applyVisibility();
  $('chart').innerHTML = forest ? `<div class="hint">Click a ${frame ? 'magenta' : 'red'} possible clearing to see its tree signal over time.</div>` : '<div class="hint">Click anywhere on the map. You\'ll see the tree and ground signals at that spot on every date, next to forest that didn\'t change.</div>';
  const s = $('date'); s.max = state.loc.dates.length - 1; s.value = state.i;
  drawPasses();
  drawStrip();
  renderAbout(state.loc, forest);
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
    map.addLayer({ id: 'esri', type: 'raster', source: 'esri', layout: { visibility: $('optical').checked ? 'visible' : 'none' } }); // satellite photo map on by default
    const response = await fetch(DATA + 'explore.json');
    if (!response.ok) throw new Error('the list of radar passes is missing');
    state.manifest = await response.json();
    if (!state.manifest.locations?.length) throw new Error('there are no places to show');
    const sel = $('loc');
    state.manifest.locations.forEach((l) => sel.append(new Option(placeName(l), l.id)));
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
    try { await loadBig(); } catch (e) { console.warn('60 km forest map not loaded', e); }
    try { await loadFrame(); } catch (e) { console.warn('frame forest map not loaded', e); }
    try { await loadExtras(); } catch (e) { ['det', 'ref', 'han'].forEach((k) => pending(k, true)); }
    await selectLoc(first.id);
    ['loc', 'date', 'opacity', 'optical', 'play', 'boundary', 'reset-map'].forEach((id) => { if ($(id)) $(id).disabled = false; });
    document.querySelectorAll('input[name=layer]').forEach((r) => (r.disabled = false));
    document.body.classList.add('ready');
    // phones: keep the map credits behind the (i) button so they do not cover the hero
    if (innerWidth <= 900) document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
  } catch (e) { $('map-status').hidden = false; $('map-status').textContent = `The map data didn't load (${e.message}). Please reload the page.`; }
  document.dispatchEvent(new Event('explore:ready')); // cinema.js waits for this (state.bigMeta stays null if loading failed)
});

$('loc').onchange = (e) => selectLoc(e.target.value).catch(() => { $('map-status').hidden = false; $('map-status').textContent = 'This place didn\'t load. Please reload the page.'; });
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
['det', 'ref', 'han', 'lost', 'prot', 'win', 'fs', 'flost', 'ffs', 'fout'].forEach((k) => ($(`t-${k}`).onchange = applyVisibility));
$('t-ref').addEventListener('change', () => { if ($('t-ref').checked) ensureRef(); });
map.on('click', (e) => {
  if (!state.loc) return;
  setMode('exploring');
  if (isForestLoc()) {
    const ls = lostSet(), layer = isFrame() ? 'flost-fill' : 'lost-fill', on = isFrame() ? $('t-flost').checked : $('t-lost').checked;
    if (ls && map.getLayer(layer) && on) {
      const r = 4;
      const hits = map.queryRenderedFeatures([[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]], { layers: [layer] })
        .map((h) => ls.byId.get(h.properties.id)).filter(Boolean);
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
map.on('error', (e) => { if (/abort/i.test(String(e && e.error && (e.error.name + ' ' + e.error.message)))) return; // a newer image replaced this one
  console.warn('map layer error', e.sourceId || '', e.error);
  $('map-status').hidden = false; $('map-status').textContent = 'A map layer didn\'t load. The other layers may still work. Check your connection or pick another layer.'; });
