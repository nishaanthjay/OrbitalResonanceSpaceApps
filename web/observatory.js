/* Presentation layer only. No detection or validation calculations are changed. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const node = (tag, text, cls) => { const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n; };
  const json = async path => { try { const r = await fetch(path); return r.ok ? await r.json() : null; } catch { return null; } };
  const fmt = n => Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: 1}) : 'Not available';
  const imagePath = (loc, layer, date) => `data/explore/${loc.id}/${layer}_${date}.webp`;
  const menu = el('menu');
  menu.onclick = () => { const open = menu.getAttribute('aria-expanded') !== 'true'; menu.setAttribute('aria-expanded', String(open)); el('navlinks').classList.toggle('open', open); };
  el('navlinks').addEventListener('click', e => { if (e.target.closest('a')) { menu.setAttribute('aria-expanded', 'false'); el('navlinks').classList.remove('open'); } });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { menu.setAttribute('aria-expanded','false'); el('navlinks').classList.remove('open'); } });
  const navLinks = [...document.querySelectorAll('#navlinks a')];
  const sections = navLinks.map(a => document.querySelector(a.getAttribute('href')));
  const trackSection = () => { let current = sections[0]; for (const s of sections) if (s.getBoundingClientRect().top <= 160) current = s; navLinks.forEach(a => { const active = a.hash === '#' + current.id; a.classList.toggle('active', active); if (active) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current'); }); };
  window.addEventListener('scroll', trackSection, {passive:true}); trackSection();
  const compactLayout = matchMedia('(max-width:800px)');
  if (compactLayout.matches) el('side').open = false;
  compactLayout.addEventListener('change', event => { if (event.matches) el('side').open = false; menu.setAttribute('aria-expanded','false'); el('navlinks').classList.remove('open'); });
  el('side').addEventListener('toggle', () => { if (typeof map !== 'undefined') map.resize(); });

  let manifest, compareVersion = 0;
  const compare = () => {
    if (!manifest) return;
    const loc = manifest.locations.find(l => l.id === el('compare-loc').value);
    const dates = loc.dates.filter((_, i) => !el('compare-layer').value.endsWith('chg') || i > 0);
    for (const id of ['before-date','after-date']) {
      const select = el(id), previous = select.value;
      select.replaceChildren(...dates.map(d => new Option(d,d)));
      select.value = dates.includes(previous) ? previous : dates[id === 'before-date' ? 0 : dates.length - 1];
      select.disabled = dates.length < 2;
    }
    updateComparison();
  };
  async function updateComparison() {
    const version = ++compareVersion;
    const loc = manifest.locations.find(l => l.id === el('compare-loc').value), layer = el('compare-layer').value;
    const before = el('before-date').value, after = el('after-date').value;
    const status = el('compare-status');
    // Hide old acquisitions immediately: never leave an old image under a new date label.
    el('before-image').hidden = el('after-image').hidden = true;
    el('before-label').textContent = before; el('after-label').textContent = after;
    if (!before || !after || before >= after) { status.hidden = false; status.textContent = 'Select a Before date earlier than the After date.'; el('swipe').disabled = true; return; }
    status.hidden = false; status.textContent = 'Loading aligned radar observations…'; el('swipe').disabled = true;
    el('compare-note').textContent = layer.endsWith('chg') ? `Change preview: each acquisition minus the mean of its own earlier dates, not a direct After − Before calculation. Blue = drop, red = rise; ±${manifest.change_range_db} dB. Values below 1 dB are transparent; preview values are derived from clipped display layers.` : `${loc.name}. ${layer === 'composite' ? 'Composite: red = HH, green = HV, blue = HH−HV.' : `${layer.toUpperCase()} gamma0 backscatter: ${loc.stretch[layer].lo} to ${loc.stretch[layer].hi} dB.`} The same display stretch and geographic bounds are used for both observations. Transparent pixels indicate no data.`;
    try {
      const loaded = await Promise.all([before,after].map(date => new Promise((resolve,reject) => { const img = new Image(); const timer = setTimeout(() => reject(new Error('Image load timed out')),15000); img.onload = () => { clearTimeout(timer); resolve(img); }; img.onerror = () => { clearTimeout(timer); reject(new Error('Image not available')); }; img.src = imagePath(loc,layer,date); })));
      if (version !== compareVersion) return;
      ['before-image','after-image'].forEach((id,i) => { el(id).src = loaded[i].src; el(id).alt = `${loc.name}, ${layer}, ${[before,after][i]}, NISAR radar`; el(id).hidden = false; });
      status.hidden = true; el('swipe').disabled = false;
    } catch { if (version !== compareVersion) return; status.textContent = 'Imagery not available for this pair. Choose another date or layer.'; }
  }
  el('compare-loc').onchange = () => { el('before-date').replaceChildren(); el('after-date').replaceChildren(); compare(); };
  el('compare-layer').onchange = compare;
  ['before-date','after-date'].forEach(id => el(id).onchange = updateComparison);
  el('swipe').oninput = e => el('comparison').style.setProperty('--split', `${e.target.value}%`);

  let detections = null, summary = null, metrics = null;
  function renderPatches() {
    const box = el('patches'); box.replaceChildren();
    if (!detections) { el('patch-count').textContent = 'Detection data not available. Restore data/detections.geojson to inspect patches.'; return; }
    const stage = el('patch-stage').value, date = el('patch-date').value;
    const features = detections.features.filter(f => (stage === 'all' || f.properties.stage === stage) && (date === 'all' || f.properties.first_date <= date));
    el('patch-count').textContent = `${features.length} map patches · all spatial splits · first observed by selected date`;
    if (!features.length) box.append(node('p','No patches match these filters.','note'));
    features.forEach(f => {
      const p = f.properties, button = node('button','', 'patch'); button.type = 'button';
      const label = node('span', `Patch ${p.id}`); label.append(node('small',`${p.first_date} · ${p.split || 'Split not available'}`));
      const detail = node('span', `${fmt(p.area_ha)} ha`, p.stage); detail.append(node('small',p.stage === 'early' ? 'Early · HH rise' : 'Late · HV drop'));
      button.append(label,detail); button.onclick = async () => {
        if (!manifest || typeof state === 'undefined' || !state.manifest || !map.getSource('radar')) { el('chart').textContent = 'Map is not ready. Wait for initialization or check your connection.'; return; }
        button.disabled = true;
        try {
          if (state.loc.id !== 'spara') { el('loc').value = 'spara'; await selectLoc('spara'); }
          const ring = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates[0][0] : f.geometry.coordinates[0];
          const bounds = ring.reduce((b,c) => [Math.min(b[0],c[0]),Math.min(b[1],c[1]),Math.max(b[2],c[0]),Math.max(b[3],c[1])],[Infinity,Infinity,-Infinity,-Infinity]);
          state.i = state.loc.dates.length - 1; el('date').value = state.i; el('t-det').checked = true; setImage(); applyVisibility();
          map.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]], {padding:80,maxZoom:15,duration:0});
          drawDetection(f,{lng:(bounds[0]+bounds[2])/2,lat:(bounds[1]+bounds[3])/2});
          el('chart').scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion:reduce)').matches ? 'instant' : 'smooth'});
        } catch { el('chart').textContent = 'Could not open this patch. Reload the map and try again.'; } finally { button.disabled = false; }
      }; box.append(button);
    });
  }
  el('patch-stage').onchange = el('patch-date').onchange = renderPatches;
  function analysis() {
    const box = el('analysis-metrics'); box.replaceChildren();
    const features = detections?.features;
    const total = features && features.every(f => Number.isFinite(f.properties.area_ha)) ? features.reduce((s,f) => s + f.properties.area_ha,0) : null;
    const rows = [['Map patches',features?.length,'Merged across dates · whole study window'],['Mapped patch area',total === null ? null : `${fmt(total)} ha`,'Sum of merged patch areas · potential disturbance'],['Early-stage patches',features?.filter(f => f.properties.stage === 'early').length,'HH rise · whole window'],['Late-stage patches',features?.filter(f => f.properties.stage === 'late').length,'HV drop · whole window']];
    rows.forEach(([title,value,note]) => { const card = node('article','', 'metric'); card.append(node('span',title),node('strong',value == null ? 'Not available' : typeof value === 'number' ? fmt(value) : value),node('small',note)); box.append(card); });
    const chart = el('area-chart'); chart.replaceChildren();
    const rowsData = summary?.per_date;
    if (!Array.isArray(rowsData) || !rowsData.length || !rowsData.every(r => typeof r.date === 'string' && ['total_area_ha','early_ha','late_ha'].every(k => Number.isFinite(r[k]) && r[k] >= 0))) { chart.append(node('p','Per-date area data not available.','note')); return; }
    const max = Math.max(...rowsData.map(r => r.total_area_ha),1);
    rowsData.forEach(r => {
      const row = node('div','', 'bar-row'); row.setAttribute('aria-label',`${r.date}: ${r.total_area_ha} hectares; early ${r.early_ha}; late ${r.late_ha}`);
      const track = node('div','', 'bar-track');
      for (const [key,cls] of [['early_ha',''],['late_ha','late']]) { const bar = node('span','',`bar-segment ${cls}`); bar.style.width = `${100*r[key]/max}%`; track.append(bar); }
      row.append(node('span',r.date.slice(5)),track,node('span',`${fmt(r.total_area_ha)} ha`,'bar-value')); chart.append(row);
    });
    chart.append(node('p','Sage: early (HH rise) · Blue-gray: late (HV drop)','note'));
    const details = document.createElement('details'), caption = node('summary','View accessible data table'), table = document.createElement('table');
    const head = document.createElement('tr'); ['Date','Patches','Area (ha)','Early (ha)','Late (ha)'].forEach(t => head.append(node('th',t))); table.append(head);
    rowsData.forEach(r => { const tr = document.createElement('tr'); [r.date,r.n_detections,r.total_area_ha,r.early_ha,r.late_ha].forEach(v => tr.append(node('td',String(v)))); table.append(tr); }); details.append(caption,table); chart.append(details);
  }
  el('download-report').onclick = () => {
    const report = {title:'The Next Frontier : frontend data report',sources:['data/detections.geojson','data/summary.json','data/metrics.json','data/explore/explore.json'],scope:'Southern Para; map patches span the whole window; agreement is scored only on holdout per-date detections.',caveats:['Radar disturbance is not confirmed deforestation.','GLAD-L alerts are a reference, not ground truth.','Optical chip labels were made by the same AI assistant that ran detection; not independently human validated.'],map_patch_count:detections?.features.length ?? null,map_patch_area_ha:detections?.features.every(f=>Number.isFinite(f.properties.area_ha)) ? detections.features.reduce((s,f)=>s+f.properties.area_ha,0) : null,summary,metrics};
    const a = document.createElement('a'), url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})); a.href=url;a.download='forest-observatory-data-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  Promise.all([json('data/explore/explore.json'),json('data/detections.geojson'),json('data/summary.json'),json('data/metrics.json')]).then(([m,d,s,met]) => {
    if (m?.locations?.length) {
      manifest = m; el('compare-loc').replaceChildren(...m.locations.map(l => new Option(l.name,l.id))); el('compare-loc').disabled = false; compare();
      const para = m.locations.find(l=>l.id==='spara'); if (para) el('patch-date').append(...para.dates.map(date=>new Option(date,date)));
    } else { el('compare-status').textContent = 'Acquisition catalog not available. Restore data/explore/explore.json.'; el('compare-layer').disabled = true; }
    detections = Array.isArray(d?.features) && d.features.every(f=>f?.geometry && f?.properties && Number.isInteger(f.properties.id) && /^\d{4}-\d{2}-\d{2}$/.test(f.properties.first_date) && ['early','late'].includes(f.properties.stage)) ? d : null;
    summary = s; metrics = met; renderPatches(); analysis();
    if (met) { el('metrics-notes').textContent = met.notes || ''; el('download-report').disabled = false; }
  }).catch(() => { el('compare-status').textContent = 'Data unavailable. Check your connection and reload.'; });
})();
