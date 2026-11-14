// story.js — guided six-chapter view of the same files explore.html uses. Reads only web/data/*; invents nothing.
'use strict';

const D = 'data/explore/';
const $ = (id) => document.getElementById(id);
const S = { loc: null, dates: [], det: null, ref: null, hansen: null, metrics: null, step: null, timer: null, picked: null };
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const map = new maplibregl.Map({
  container: 'map', style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [-54.699, -8.1995], zoom: 11.3, attributionControl: { compact: true }, cooperativeGestures: window.innerWidth < 820,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

const corners = (b) => [[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]];
const img = (layer, i) => `${D}${S.loc.id}/${layer}_${S.dates[i]}.webp`;
async function json(p) { try { const r = await fetch(p); return r.ok ? r.json() : null; } catch { return null; } }
const fmtDate = (d) => new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

function vis(id, on) { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'); }
function setRadar(layer, i, opacity = 1) {
  map.getSource('radar').updateImage({ url: img(layer, i), coordinates: corners(S.loc.bounds_lonlat) });
  map.setPaintProperty('radar', 'raster-opacity', opacity);
}
function setChange(i) {
  if (i === 0) { vis('chg', false); return; }
  map.getSource('chg').updateImage({ url: img('hvchg', i), coordinates: corners(S.loc.bounds_lonlat) });
  vis('chg', true);
}
function ticker(text) { const t = $('ticker'); t.style.display = text ? 'block' : 'none'; t.textContent = text || ''; }
function stopPlay() { clearInterval(S.timer); S.timer = null; }
function fit(pad = 40) { const b = S.loc.bounds_lonlat; map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: pad, duration: reduceMotion ? 0 : 1200 }); }

// ---------- chapters ----------
const last = () => S.dates.length - 1;
const STEPS = {
  intro() { setRadar('hv', last()); vis('chg', false); vis('hansen', false); vis('det-fill', false); vis('det-line', false); vis('ref', false); ticker(''); },
  see() { setRadar('hv', last()); vis('chg', false); vis('hansen', false); detLayers(false); ticker(fmtDate(S.dates[last()])); fit(); },
  forest() { setRadar('hv', last()); vis('chg', false); vis('hansen', !!S.hansen); detLayers(false); ticker('Hansen forest loss 2021–2025 over radar'); fit(); },
  change() { vis('hansen', false); detLayers(false); fit(); play(); },
  patch() { vis('hansen', false); vis('chg', false); setRadar('hv', last()); showPatch(); },
  truth() { stopPlay(); setRadar('hv', last(), 0.75); vis('chg', false); vis('hansen', !!S.hansen); detLayers(true); ticker('Our flags vs GLAD alerts, June–October 2026'); fit(); },
  next() { stopPlay(); setRadar('composite', last()); vis('chg', false); vis('hansen', false); detLayers(false); ticker(''); fit(); },
};
function detLayers(on) { vis('det-fill', on && !!S.det); vis('det-line', on && !!S.det); vis('ref', on && !!S.ref); }

function play() {
  stopPlay();
  let i = 1;
  const frame = () => { setRadar('hv', i, 0.55); setChange(i); ticker(`${fmtDate(S.dates[i])}, change vs earlier passes`); };
  if (reduceMotion) { i = last(); frame(); return; }
  frame();
  S.timer = setInterval(() => { i += 1; if (i > last()) { stopPlay(); return; } frame(); }, 1100);
}

// ---------- chapter 4: one patch ----------
function pickPatch() { // the flagged patch with the largest HV drop (mean of last 2 passes vs first 3); stated in the text
  let best = null, bestDrop = -Infinity;
  for (const f of S.det.features) {
    const hv = f.properties.hv_series_db;
    if (!Array.isArray(hv) || hv.length !== S.dates.length || hv.some((v) => typeof v !== 'number')) continue;
    const drop = (hv[0] + hv[1] + hv[2]) / 3 - (hv[hv.length - 1] + hv[hv.length - 2]) / 2;
    if (drop > bestDrop) { bestDrop = drop; best = f; }
  }
  return best;
}
function centroid(geom) {
  const ring = geom.type === 'Polygon' ? geom.coordinates[0] : geom.coordinates[0][0];
  let x = 0, y = 0; ring.forEach(([a, b]) => { x += a; y += b; }); return [x / ring.length, y / ring.length];
}
function showPatch() {
  if (!S.det) { $('chart').innerHTML = '<p class="small">Flagged patches are not available right now.</p>'; return; }
  const f = S.picked || (S.picked = pickPatch());
  if (!f) return;
  const p = f.properties, c = centroid(f.geometry);
  map.flyTo({ center: c, zoom: 14.2, duration: reduceMotion ? 0 : 1600 });
  detLayers(true); vis('ref', false);
  map.setFilter('det-sel', ['==', ['get', 'id'], p.id]); vis('det-sel', true);
  ticker(`Patch ${p.id}: ${p.area_ha} ha, first flagged ${fmtDate(p.first_date)}`);
  $('chart').innerHTML = chart(p.hh_series_db, p.hv_series_db, S.loc.stable_forest_ref);
}
function chart(hh, hv, ref) {
  const W = 360, H = 210, ml = 34, mr = 10, mt = 12, mb = 28, dates = S.dates;
  const all = hh.concat(hv, ref.hh, ref.hv), lo = Math.floor(Math.min(...all)) - 1, hi = Math.ceil(Math.max(...all)) + 1;
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[last()]);
  const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr), Y = (v) => mt + (hi - v) / (hi - lo) * (H - mt - mb);
  const line = (vals, col, dash) => `<polyline fill="none" stroke="${col}" stroke-width="${dash ? 1.5 : 2.5}" ${dash ? 'stroke-dasharray="4 3"' : ''} points="${vals.map((v, i) => `${X(dates[i])},${Y(v)}`).join(' ')}"/>`;
  const dots = (vals, col) => vals.map((v, i) => `<circle cx="${X(dates[i])}" cy="${Y(v)}" r="3.2" fill="${col}"/>`).join('');
  let g = '';
  for (let v = Math.ceil(lo); v <= hi; v += 2) g += `<line x1="${ml}" x2="${W - mr}" y1="${Y(v)}" y2="${Y(v)}" stroke="#d6dde2"/><text x="${ml - 5}" y="${Y(v) + 4}" font-size="11" fill="#4a5a66" text-anchor="end" font-family="Archivo">${v}</text>`;
  const months = dates.map((d, i) => (i % 2 === 0 ? `<text x="${X(d)}" y="${H - 9}" font-size="11" fill="#4a5a66" text-anchor="middle" font-family="Archivo">${new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}</text>` : '')).join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Radar signal over nine passes for this patch, forest signal and ground signal, compared with typical stable forest">
    ${g}${months}<text x="6" y="${mt + 2}" font-size="10" fill="#4a5a66" font-family="Archivo" transform="rotate(-90 6 ${mt + 2})" text-anchor="end">dB</text>
    ${line(ref.hv, '#4a5a66', true)}${line(ref.hh, '#4a5a66', true)}${line(hv, '#2f6b4f')}${line(hh, '#b4401c')}${dots(hv, '#2f6b4f')}${dots(hh, '#b4401c')}</svg>`;
}

// ---------- numbers from files ----------
function fillNumbers() {
  const m = S.metrics;
  if (m && m.agreement && m.agreement.split === 'holdout' && Number.isFinite(m.agreement.precision_like) && Number.isFinite(m.n_detections)) {
    $('fAgree').textContent = `${Math.round(m.agreement.precision_like * m.n_detections)} of ${m.n_detections}`;
  }
  const h = m && m.hand_labeled;
  if (h && Number.isFinite(h.n_sample) && Number.isFinite(h.n_unsure) && Number.isFinite(h.precision)) {
    const usable = h.n_sample - h.n_unsure;
    $('handNote').textContent = `Photo check: 45 points, labelled blind to which were flags; 0 of 20 checkable flags across both halves showed clearing (validation/results_final.md). Held-back half alone: ${Math.round(h.precision * usable)} of ${usable} checkable flags cleared; ${h.n_unsure} of ${h.n_sample} had no clear photo. Labelled by our AI assistant, not yet by an independent person.`;
  }
  if (S.hansen && S.hansen.years) {
    $('hansenKey').innerHTML = Object.entries(S.hansen.years).filter(([y, c]) => /^\d{4}$/.test(y) && /^#[0-9a-fA-F]{3,8}$/.test(c)).map(([y, c]) => `<span><i style="background:${c}"></i>${y}</span>`).join('');
  }
}

// ---------- scroll driving ----------
function observe() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const step = e.target.dataset.step;
      if (step === S.step) return;
      S.step = step;
      document.querySelectorAll('.chapter').forEach((c) => c.classList.toggle('active', c === e.target));
      if (step !== 'intro') $('clouds').classList.add('cleared');
      if (step !== 'change') stopPlay();
      if (step !== 'patch') vis('det-sel', false);
      STEPS[step]();
    });
  }, { rootMargin: '-45% 0px -45% 0px' });
  document.querySelectorAll('.chapter').forEach((c) => io.observe(c));
}

map.on('load', async () => {
  const manifest = await json(D + 'explore.json');
  S.loc = manifest.locations.find((l) => l.id === 'spara');
  S.dates = S.loc.dates;
  [S.det, S.ref, S.hansen, S.metrics] = await Promise.all([json('data/detections.geojson'), json('data/reference_alerts.geojson'), json(`${D}spara/hansen_loss.json`), json('data/metrics.json')]);

  map.addSource('esri', { type: 'raster', tileSize: 256, maxzoom: 18, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'] });
  map.addLayer({ id: 'esri', type: 'raster', source: 'esri', layout: { visibility: 'none' } });
  const c = corners(S.loc.bounds_lonlat);
  map.addSource('radar', { type: 'image', url: img('hv', last()), coordinates: c });
  map.addLayer({ id: 'radar', type: 'raster', source: 'radar', paint: { 'raster-fade-duration': 0 } });
  map.addSource('chg', { type: 'image', url: img('hvchg', last()), coordinates: c });
  map.addLayer({ id: 'chg', type: 'raster', source: 'chg', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } });
  if (S.hansen) {
    map.addSource('hansen', { type: 'image', url: `${D}spara/hansen_loss.webp`, coordinates: c });
    map.addLayer({ id: 'hansen', type: 'raster', source: 'hansen', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } });
  }
  if (S.ref) {
    map.addSource('ref', { type: 'geojson', data: S.ref });
    map.addLayer({ id: 'ref', type: 'line', source: 'ref', layout: { visibility: 'none' }, paint: { 'line-color': '#22d3ee', 'line-width': 1 } });
  }
  if (S.det) {
    map.addSource('det', { type: 'geojson', data: S.det });
    const col = ['match', ['get', 'stage'], 'early', '#f59e0b', 'late', '#be123c', '#999'];
    map.addLayer({ id: 'det-fill', type: 'fill', source: 'det', layout: { visibility: 'none' }, paint: { 'fill-color': col, 'fill-opacity': 0.75 } });
    map.addLayer({ id: 'det-line', type: 'line', source: 'det', layout: { visibility: 'none' }, paint: { 'line-color': col, 'line-width': 1.2 } });
    map.addLayer({ id: 'det-sel', type: 'line', source: 'det', layout: { visibility: 'none' }, paint: { 'line-color': '#ffffff', 'line-width': 3 } });
  }
  fillNumbers();
  [1, 2, 3, 4, 5, 6, 7, 8].forEach((i) => { const im = new Image(); im.src = img('hvchg', i); const im2 = new Image(); im2.src = img('hv', i); });
  observe();
});

$('start').onclick = () => {
  $('clouds').classList.add('cleared');
  document.querySelector('[data-step="see"]').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
};
$('optical').onclick = (e) => {
  const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
  e.currentTarget.setAttribute('aria-pressed', on);
  e.currentTarget.textContent = on ? 'Back to radar' : 'Compare with an optical photo';
  vis('esri', on);
  map.setPaintProperty('radar', 'raster-opacity', on ? 0 : 1);
};
$('replay').onclick = () => play();
