// Static MapLibre viewer. Reads files in web/data/ (see CONTRACTS.md). Missing files show "data not loaded yet".
const $ = (id) => document.getElementById(id);
const NOT_LOADED = 'data not loaded yet';

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty', // free, no API key
  center: [0, 0], // TODO: set to the AOI from CLAUDE.md
  zoom: 2,
});

async function getJSON(path) {
  try {
    const r = await fetch(path);
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

function markMissing(statusId) { $(statusId).textContent = NOT_LOADED; }

function addGeoJSON(id, data, paint, type = 'fill') {
  map.addSource(id, { type: 'geojson', data });
  map.addLayer({ id, type, source: id, paint });
}

function setVisible(id, on) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

map.on('load', async () => {
  const [det, ref, metrics] = await Promise.all([
    getJSON('data/detections.geojson'),
    getJSON('data/reference_alerts.geojson'),
    getJSON('data/metrics.json'),
  ]);

  if (det) {
    addGeoJSON('det', det, { 'fill-color': '#e11d48', 'fill-opacity': 0.5, 'fill-outline-color': '#9f1239' });
    setupDates(det);
  } else markMissing('s-det');

  if (ref) {
    addGeoJSON('ref', ref, { 'fill-color': '#2563eb', 'fill-opacity': 0.4 });
    setVisible('ref', $('t-ref').checked);
  } else markMissing('s-ref');

  if (metrics) showMetrics(metrics); else $('metrics').textContent = NOT_LOADED;

  // TODO: HH/HV change layers need a COG renderer for web/data/change_{hh,hv}_<date>.tif.
  markMissing('s-hh');
  markMissing('s-hv');
  $('t-hh').disabled = $('t-hv').disabled = true;
});

$('t-det').onchange = (e) => setVisible('det', e.target.checked);
$('t-ref').onchange = (e) => setVisible('ref', e.target.checked);

function showMetrics(m) {
  const f = (v) => (typeof v === 'number' ? v.toFixed(2) : '?');
  $('metrics').innerHTML =
    `Precision ${f(m.precision)}<br>Recall ${f(m.recall)}<br>F1 ${f(m.f1)}<br>` +
    `Detections ${m.n_detections ?? '?'} / reference ${m.n_reference ?? '?'}<br>` +
    `Source: ${m.reference_source ?? '?'}` + (m.notes ? `<br><em>${m.notes}</em>` : '');
}

// Date slider filters detections by their `date` property (<= selected date).
function setupDates(det) {
  const dates = [...new Set(det.features.map((f) => f.properties.date))].sort();
  if (!dates.length) return;
  const s = $('date-slider');
  s.min = 0; s.max = dates.length - 1; s.value = dates.length - 1; s.disabled = false;
  const apply = () => {
    const d = dates[s.value];
    $('date-label').textContent = d;
    map.setFilter('det', ['<=', ['get', 'date'], d]);
  };
  s.oninput = apply;
  apply();
}
