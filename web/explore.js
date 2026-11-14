// explore.js — NISAR surface-change explorer. Reads only files written by web/tools/make_explore.py.
// No data is invented here: every pixel and number comes from web/data/explore/ or validation/fnf_metrics.json values
// copied into the story text below (with the file named).
'use strict';

const DATA = 'data/explore/';
const R = 6378137;
const $ = (id) => document.getElementById(id);
const state = { manifest: null, loc: null, i: 0, layer: 'composite', series: null, playing: null, marker: null };

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
function url(layer, i) { return `${DATA}${state.loc.id}/${layer}_${state.loc.dates[i]}.webp`; }

function setImage() {
  const loc = state.loc, c = corners(loc.bounds_lonlat), op = +$('opacity').value / 100;
  const isChg = state.layer.endsWith('chg');
  // base radar image: the chosen layer, or HV under a change layer
  map.getSource('radar').updateImage({ url: url(isChg ? 'hv' : state.layer, state.i), coordinates: c });
  map.setPaintProperty('radar', 'raster-opacity', isChg ? 0.45 * op : op);
  const showChg = isChg && hasImage(state.layer, state.i);
  if (showChg) map.getSource('chg').updateImage({ url: url(state.layer, state.i), coordinates: c });
  map.setPaintProperty('chg', 'raster-opacity', showChg ? 1 : 0);
  $('datelabel').textContent = loc.dates[state.i] + (isChg && !showChg ? '  (first date: nothing earlier to compare)' : '');
  drawLegend();
  if (state.lastClick) drawChart(...state.lastClick);
}

function preload() { // so the slider and play are smooth
  for (const layer of ['composite', 'hv', 'hh', 'hvchg', 'hhchg'])
    state.loc.dates.forEach((_, i) => { if (hasImage(layer, i)) { const im = new Image(); im.src = url(layer, i); } });
}

function drawLegend() {
  const s = state.loc.stretch, L = state.layer, el = $('legend');
  const bar = (css, lo, hi, unit) => `<div class="legend" style="background:${css}"></div><div class="legend-lab"><span>${lo}</span><span>${hi}</span></div><div class="note">${unit}</div>`;
  if (L === 'hv' || L === 'hh') el.innerHTML = bar('linear-gradient(90deg,#000,#fff)', `${s[L].lo} dB`, `${s[L].hi} dB`, `${L.toUpperCase()} gamma0, one fixed stretch for all dates (values outside are clipped)`);
  else if (L.endsWith('chg')) el.innerHTML = bar('linear-gradient(90deg,#00f,#fff,#f00)', `-${state.manifest.change_range_db} dB (drop)`, `+${state.manifest.change_range_db} dB (rise)`, 'This date minus the mean of all earlier dates. Computed on ~80 m cells; changes under 1 dB are transparent (per-date noise ~0.4 dB at 20 m). Display preview from the clipped layers: real drops can be larger.');
  else el.innerHTML = `<div class="note">Red = HH (${s.hh.lo} to ${s.hh.hi} dB), green = HV (${s.hv.lo} to ${s.hv.hi} dB), blue = HH&minus;HV (${s.ratio.lo} to ${s.ratio.hi} dB). Green/yellow = forest, purple/blue = cleared or bare.</div>`;
}

// ---------- time series ----------
async function loadSeries() {
  const r = await fetch(`${DATA}${state.loc.id}/series.bin`);
  state.series = new Uint8Array(await r.arrayBuffer());
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

function drawChart(lon, lat) {
  state.lastClick = [lon, lat];
  const c = cellAt(lon, lat), el = $('chart');
  if (!c || !state.series) { el.innerHTML = '<div class="hint">Outside the radar window. Click inside the image.</div>'; return; }
  const v = valuesAt(...c), ref = state.loc.stable_forest_ref, dates = state.loc.dates;
  const all = [...v.hh, ...v.hv].filter(Boolean).map((p) => p.db).concat(ref.hh, ref.hv);
  if (!v.hv.some(Boolean)) { el.innerHTML = '<div class="hint">No radar data at this spot.</div>'; return; }
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
  const clippedAny = [...v.hh, ...v.hv].some((p) => p && p.clipped);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="HH and HV backscatter over time at the clicked spot">${grid}${ticks}${cur}
    ${line(ref.hh, '#f28b82', true)}${line(ref.hv, '#81c995', true)}${line(v.hh, '#f28b82')}${line(v.hv, '#81c995')}${dots(v.hh, '#f28b82')}${dots(v.hv, '#81c995')}</svg>
    <div class="note"><b style="color:#f28b82">HH</b> and <b style="color:#81c995">HV</b> (dB) at ${lat.toFixed(4)}, ${lon.toFixed(4)}, ~80 m cell. Dashed = stable radar forest (median of ${ref.n_pixels.toLocaleString()} px with HV &ge; ${state.manifest.t_db_forest.toFixed(2)} dB on every date). Clearing usually shows as HV falling away from the dashed line.</div>
    ${clippedAny ? '<div class="warn">Hollow dots hit the display stretch limit: the true value is at or beyond it.</div>' : ''}`;
  if (state.marker) state.marker.setLngLat([lon, lat]); else state.marker = new maplibregl.Marker({ color: '#fdd663' }).setLngLat([lon, lat]).addTo(map);
}

// ---------- story ----------
function story() {
  $('story').innerHTML = `
    <p><b>The new frontier, twice.</b> The place: the forest edge along the BR-163 highway near Novo Progresso, Pará, a frontier town where forest is being cut for cattle pasture (Mongabay; see submission/sources.md). The sensor: NISAR's L-band radar, which sees through the cloud that hides this forest from optical satellites for much of the year.</p>
    <p><b>Radar separates forest from cleared land.</b> One HV threshold, chosen on the north half of the window and tested once on the south half, put 83.1% of 100 m blocks in the same class as the Hansen forest map (kappa 0.66), against 52.4% for calling everything forest. The same threshold, unchanged, scored 95.6% in Rondônia. <span class="note">(validation/fnf_metrics.json; pre-registered in validation/PREREG_fnf.md. This is agreement with an optical map that ends in 2025, not ground truth.)</span></p>
    <p><b>Catching new clearing is harder, and we say so.</b> Early checks suggest clearing shows up as HV falling and HH rising, but the radar lags behind optical alerts, and most 2026 alerts here flag land that was already cleared. <span class="tag">numbers pending</span> Final detection agreement and hand-checked precision are added after the last run.</p>
    <p class="note">We do not claim this stops deforestation or works everywhere. Rain, fire, flooding and selective logging are not handled.</p>`;
}

// ---------- setup ----------
async function selectLoc(id) {
  state.loc = state.manifest.locations.find((l) => l.id === id);
  state.i = state.loc.dates.length - 1;
  state.lastClick = null;
  $('chart').innerHTML = '<div class="hint">Click the map to see HH and HV over all dates at that spot, next to stable forest.</div>';
  const s = $('date'); s.max = state.loc.dates.length - 1; s.value = state.i;
  $('about').textContent = `${state.loc.name}. ${state.loc.notes} Change previews and time series are computed from these display layers (web/tools/make_explore.py), not from detect.py.`;
  const b = state.loc.bounds_lonlat;
  map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 30, duration: 0 });
  await loadSeries();
  setImage();
  preload();
}

map.on('load', async () => {
  map.addSource('esri', { type: 'raster', tileSize: 256, maxzoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'] });
  map.addLayer({ id: 'esri', type: 'raster', source: 'esri', layout: { visibility: 'none' } });
  state.manifest = await (await fetch(DATA + 'explore.json')).json();
  const sel = $('loc');
  state.manifest.locations.forEach((l) => sel.append(new Option(`${l.name} (${l.dates.length} dates)`, l.id)));
  const first = state.manifest.locations[0];
  map.addSource('radar', { type: 'image', url: `${DATA}${first.id}/composite_${first.dates[first.dates.length - 1]}.webp`, coordinates: corners(first.bounds_lonlat) });
  map.addLayer({ id: 'radar', type: 'raster', source: 'radar', paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  map.addSource('chg', { type: 'image', url: `${DATA}${first.id}/hvchg_${first.dates[first.dates.length - 1]}.webp`, coordinates: corners(first.bounds_lonlat) });
  map.addLayer({ id: 'chg', type: 'raster', source: 'chg', paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest', 'raster-opacity': 0 } });
  story();
  await selectLoc(first.id);
});

$('loc').onchange = (e) => selectLoc(e.target.value);
$('date').oninput = (e) => { state.i = +e.target.value; setImage(); };
$('opacity').oninput = () => setImage();
$('optical').onchange = (e) => map.setLayoutProperty('esri', 'visibility', e.target.checked ? 'visible' : 'none');
document.querySelectorAll('input[name=layer]').forEach((r) => (r.onchange = () => { state.layer = r.value; setImage(); }));
map.on('click', (e) => drawChart(e.lngLat.lng, e.lngLat.lat));
$('play').onclick = () => {
  if (state.playing) { clearInterval(state.playing); state.playing = null; $('play').innerHTML = '&#9654;'; return; }
  $('play').innerHTML = '&#10074;&#10074;';
  state.playing = setInterval(() => { state.i = (state.i + 1) % state.loc.dates.length; $('date').value = state.i; setImage(); }, 900);
};
