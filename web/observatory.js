/* Presentation layer only. No detection or validation calculations are changed. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const node = (tag, text, cls) => { const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n; };
  const json = async path => { try { const r = await fetch(path); return r.ok ? await r.json() : null; } catch { return null; } };
  const fmt = n => Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: 1}) : 'Not available';
  const imagePath = (loc, layer, date) => `data/explore/${loc.id}/${layer}_${date}.webp`;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // nav: a glass highlight that glides to the hovered link and rests on the section in view
  const nav = document.querySelector('.top nav'), blob = el('nav-blob');
  const navLinks = [...nav.querySelectorAll('a[href^="#"]')];
  const sections = navLinks.map(a => document.querySelector(a.getAttribute('href')));
  let hovered = null, current = null;
  const glide = () => {
    const target = hovered || current;
    if (!target) { blob.style.opacity = 0; return; }
    blob.style.opacity = 1; blob.style.transform = `translateX(${target.offsetLeft}px)`; blob.style.width = `${target.offsetWidth}px`;
  };
  nav.querySelectorAll('a').forEach(a => { a.addEventListener('pointerenter', () => { hovered = a; glide(); }); a.addEventListener('focus', () => { hovered = a; glide(); }); });
  nav.addEventListener('pointerleave', () => { hovered = null; glide(); });
  nav.addEventListener('focusout', e => { if (!nav.contains(e.relatedTarget)) { hovered = null; glide(); } });
  const trackSection = () => {
    // the nav order is not the page order (Evidence sits above Detection): pick the section that passed the line most recently, not the last one in nav order
    let s = null, best = -Infinity; for (const sec of sections) { const t = sec.getBoundingClientRect().top; if (t <= innerHeight * 0.35 && t > best) { s = sec; best = t; } }
    const a = navLinks[sections.indexOf(s)] || null;
    if (a !== current) {
      navLinks.forEach(l => { l.classList.toggle('active', l === a); if (l === a) l.setAttribute('aria-current', 'location'); else l.removeAttribute('aria-current'); });
      current = a; glide();
      if (a && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: a.offsetLeft - 40, behavior: reduced ? 'auto' : 'smooth' });
    }
    document.body.classList.toggle('scrolled', scrollY > innerHeight * 0.6);
  };
  addEventListener('scroll', trackSection, {passive:true}); addEventListener('resize', trackSection); trackSection();

  // scroll reveal: sections rise in once as they enter the viewport
  if ('IntersectionObserver' in window && !reduced) {
    document.documentElement.classList.add('js-reveal');
    const io = new IntersectionObserver(entries => entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -10% 0px' });
    document.querySelectorAll('.reveal').forEach(n => io.observe(n));
  } else document.querySelectorAll('.reveal').forEach(n => n.classList.add('in'));

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
    } catch { if (version !== compareVersion) return; status.textContent = 'No imagery for this pair. Try another date or layer.'; }
  }
  el('compare-loc').onchange = () => { el('before-date').replaceChildren(); el('after-date').replaceChildren(); compare(); };
  el('compare-layer').onchange = compare;
  ['before-date','after-date'].forEach(id => el(id).onchange = updateComparison);
  el('swipe').oninput = e => el('comparison').style.setProperty('--split', `${e.target.value}%`);

  let detections = null, summary = null, metrics = null, openPatch = null;
  function renderPatches() {
    const box = el('patches'); box.replaceChildren();
    if (!detections) { el('patch-count').textContent = 'Detection data not available. Restore data/detections.geojson to inspect patches.'; return; }
    const stage = el('patch-stage').value, date = el('patch-date').value;
    const features = detections.features.filter(f => (stage === 'all' || f.properties.stage === stage) && (date === 'all' || f.properties.first_date <= date));
    el('patch-count').textContent = `${features.length} map patches · all spatial splits · first observed by selected date`;
    if (!features.length) box.append(node('p','No patches match these filters.','note'));
    features.forEach(f => {
      const p = f.properties, button = node('button','', 'patch'); button.type = 'button';
      if (p.id === openPatch) button.setAttribute('aria-current', 'true');
      const label = node('span', `Patch ${p.id}`); label.append(node('small',`${p.first_date} · ${p.split || 'Split not available'}`));
      const detail = node('span', `${fmt(p.area_ha)} ha`, p.stage); detail.append(node('small',p.stage === 'early' ? 'Early · HH rise' : 'Late · HV drop'));
      button.append(label,detail); button.onclick = async () => {
        if (!manifest || typeof state === 'undefined' || !state.manifest || !map.getSource('radarA')) { el('patch-count').textContent = 'Map is not ready yet. Wait a moment and try again.'; return; }
        button.disabled = true;
        openPatch = p.id; box.querySelectorAll('.patch').forEach(b => b.removeAttribute('aria-current')); button.setAttribute('aria-current', 'true');
        try {
          if (state.loc.id !== 'spara') { el('loc').value = 'spara'; await selectLoc('spara'); }
          const ring = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates[0][0] : f.geometry.coordinates[0];
          const bounds = ring.reduce((b,c) => [Math.min(b[0],c[0]),Math.min(b[1],c[1]),Math.max(b[2],c[0]),Math.max(b[3],c[1])],[Infinity,Infinity,-Infinity,-Infinity]);
          state.i = state.loc.dates.length - 1; el('date').value = state.i; el('t-det').checked = true; applyVisibility();
          toTop(); setMode('exploring'); setImage(false);
          focusBounds(bounds);
          drawDetection(f,{lng:(bounds[0]+bounds[2])/2,lat:(bounds[1]+bounds[3])/2});
        } catch { el('chart').textContent = 'This patch wouldn\'t open. Reload the map and try again.'; } finally { button.disabled = false; }
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
    countUp(box);
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
  // metric values count up once, the first time the grid scrolls into view (the final text is the same fmt() output)
  function countUp(box) {
    if (reduced || !('IntersectionObserver' in window)) return;
    const items = [...box.querySelectorAll('strong')].map(n => { const m = n.textContent.match(/^([\d,.]+)(.*)$/); return m ? { n, to: Number(m[1].replace(/,/g, '')), rest: m[2], text: n.textContent } : null; }).filter(i => i && Number.isFinite(i.to));
    if (!items.length) return;
    const io = new IntersectionObserver(([e]) => { // fires with the scroll reveal, while the grid is still faded out
      if (!e.isIntersecting) return; io.disconnect();
      const t0 = performance.now(), D = 1200;
      const step = now => { const k = Math.min(1, (now - t0) / D), ease = 1 - Math.pow(1 - k, 4);
        items.forEach(i => { i.n.textContent = k < 1 ? `${fmt(Number.isInteger(i.to) ? Math.round(i.to * ease) : i.to * ease)}${i.rest}` : i.text; });
        if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    }, { rootMargin: '0px 0px -10% 0px' });
    io.observe(box);
  }
  el('download-report').onclick = () => {
    const report = {title:'The Next Frontier : frontend data report',sources:['data/detections.geojson','data/summary.json','data/metrics.json','data/explore/explore.json'],scope:'Southern Para; map patches span the whole window; agreement is scored only on holdout per-date detections.',caveats:['Radar disturbance is not confirmed deforestation.','GLAD-L alerts are a reference, not ground truth.','The same AI assistant that ran detection also labelled the optical chips. No independent person has checked them.'],map_patch_count:detections?.features.length ?? null,map_patch_area_ha:detections?.features.every(f=>Number.isFinite(f.properties.area_ha)) ? detections.features.reduce((s,f)=>s+f.properties.area_ha,0) : null,summary,metrics};
    const a = document.createElement('a'), url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})); a.href=url;a.download='forest-observatory-data-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  // ================= headline results: every number below is read from these files at runtime =================
  // big.json / frame.json (scores copied from validation/scale_metrics.json / frame_metrics.json), big/cloud.json,
  // data/metrics.json, and explore/headline.json (values that only exist in validation/, each with its source + path).
  const pc = (v, d = 1) => Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : 'n/a';
  const int = v => Number.isFinite(v) ? Math.round(v).toLocaleString('en') : 'n/a';
  const times = (a, b) => Number.isFinite(a) && Number.isFinite(b) && b > 0 ? `${(a / b).toFixed(1)}×` : 'n/a';
  const nfPR = c => c && [c.tn / (c.tn + c.fn), c.tn / (c.tn + c.fp)]; // non-forest precision, recall from counts
  const fill = (id, nodes) => { const b = el(id); if (b) b.replaceChildren(...nodes); };
  const H = {};

  function facts() {
    const big = H.big?.scores?.forest_map_vs_hansen, fr = H.frame?.scores, fm = fr?.a_forest_map?.median, gl = fr?.b_alerts?.['GLAD-L'];
    const sc = H.cloud?.scenes, cl = Array.isArray(sc) ? sc.filter(s => s.clear_fraction_aoi < 0.02).length : null;
    const np = H.cloud?.nisar_passes?.length;
    const item = (k, big1, vs, txt) => { const a = node('article', '', 'fact'); a.append(node('span', k, 'k'), node('strong', big1), node('span', vs, 'vs'), node('small', txt)); return a; };
    fill('facts', [
      item('60 km forest map', pc(big?.oa), `vs ${pc(big?.all_forest_baseline)} if you call everything forest`, 'Agreement with the Hansen forest map, 9-pass median, out of sample.'),
      item(`Full NISAR frame, ${int(fr?.blocks?.scored_km2)} km² scored`, pc(fm?.oa), `vs ${pc(fm?.all_forest_baseline)} all-forest baseline`, `Same fixed threshold, scored once. Kappa ${Number.isFinite(fm?.kappa) ? fm.kappa.toFixed(2) : 'n/a'}.`),
      item('Flagged blocks, full frame', times(gl?.lost?.precision_like, gl?.control?.precision_like), `more likely than random stable forest to overlap a GLAD-L alert (${pc(gl?.lost?.precision_like)} vs ${pc(gl?.control?.precision_like, 2)})`, 'Enrichment, not accuracy: flags are unconfirmed.'),
      item('Dry season, June to October', np ? `${np} of ${np}` : 'n/a', `radar passes usable · Sentinel-2: ${cl ?? 'n/a'} of ${sc?.length ?? 'n/a'} scenes fully clouded (clear < 2%)`, 'Sentinel-2 still saw this area well most of the time.'),
    ]);
  }

  function scales() {
    const hd = H.head, T = hd?.T_db?.value, tb = hd?.tune_blocks?.value;
    el('scales-threshold').textContent = Number.isFinite(T)
      ? `One HV threshold (${T.toFixed(2)} dB), set on a ${Number.isFinite(tb) ? `${int(tb / 100)} km² strip (${int(tb)} blocks, ` : ''}the north half of the 20 km window${Number.isFinite(tb) ? ')' : ''}, never refit.`
      : 'Threshold pending (headline.json).';
    const rows = [
      ['20 km window, held-out half', hd?.fnf_holdout_20km?.value, 'validation/fnf_metrics.json holdout.all'],
      ['Rondônia, 20 km (transfer)', hd?.rondonia_transfer?.value, 'validation/fnf_metrics.json transfer_rondonia.all'],
      ['60 km, BR-163 frontier', H.big?.scores?.forest_map_vs_hansen, 'big.json scores.forest_map_vs_hansen'],
      ['Full NISAR frame', H.frame?.scores?.a_forest_map?.median, 'frame.json scores.a_forest_map.median'],
    ];
    const t = el('scales'); t.replaceChildren();
    const thead = document.createElement('thead'), hr = document.createElement('tr');
    ['Scale', 'Area scored', 'Agreement', 'All-forest baseline', 'Kappa', 'Forest P / R', 'Non-forest P / R'].forEach(h => hr.append(node('th', h)));
    thead.append(hr); t.append(thead);
    const tb2 = document.createElement('tbody');
    rows.forEach(([label, c, src]) => {
      const tr = document.createElement('tr'); tr.title = src;
      if (!c) { tr.append(node('td', label), node('td', 'pending')); tb2.append(tr); return; }
      const [np, nr] = nfPR(c);
      [label, `${int(c.n / 100)} km²`, pc(c.oa), pc(c.all_forest_baseline), c.kappa.toFixed(2), `${pc(c.forest_precision)} / ${pc(c.forest_recall)}`, `${pc(np)} / ${pc(nr)}`]
        .forEach((v, i) => tr.append(node(i ? 'td' : 'th', v)));
      tb2.append(tr);
    });
    t.append(tb2);
    el('scales-note').textContent = 'Area = scored 100 m blocks (1 ha each). P / R = precision / recall against Hansen, non-forest computed from the confusion counts. The 60 km row excludes the 20 km window; Rondônia is a different area with the threshold unchanged. Sources: hover a row, or validation/results_final.md.';
  }

  function validation() {
    const big = H.big?.scores?.forest_map_vs_hansen, fm = H.frame?.scores?.a_forest_map?.median;
    const dl = node('dl', '', 'kv');
    [['60 km map, agreement (all-forest baseline)', big && `${pc(big.oa)} (${pc(big.all_forest_baseline)}) · kappa ${big.kappa.toFixed(2)}`],
     ['Full frame, agreement (all-forest baseline)', fm && `${pc(fm.oa)} (${pc(fm.all_forest_baseline)}) · kappa ${fm.kappa.toFixed(2)}`],
     ['Full frame, non-forest precision', fm && pc(nfPR(fm)[0])]].forEach(([k, v]) => dl.append(node('dt', k), node('dd', v || 'pending')));
    fill('val-forest', [dl]);
    const t = document.createElement('table'), hr = document.createElement('tr');
    ['Area', 'Alerts', 'Flagged blocks', 'With alert', 'Random stable forest', 'Ratio'].forEach(h => hr.append(node('th', h)));
    t.append(hr);
    for (const [name, al] of [['60 km', H.big?.scores?.alerts], ['Full frame', H.frame?.scores?.b_alerts]]) for (const src of ['GLAD-L', 'GLAD-S2']) {
      const a = al?.[src], tr = document.createElement('tr');
      [name, src, int(a?.lost?.n_blocks), pc(a?.lost?.precision_like), pc(a?.control?.precision_like, 2), times(a?.lost?.precision_like, a?.control?.precision_like)].forEach(v => tr.append(node('td', v)));
      t.append(tr);
    }
    fill('val-enrich', [t]);
  }

  function detector() { // the failed first attempt, from data/metrics.json + headline.json detector
    const m = metrics, d = H.head?.detector?.value, box = el('results');
    if (!m?.agreement || m.agreement.split !== 'holdout') { fill('results', [node('span', 'pending', 'tag')]); return; }
    const a = m.agreement, agree = Math.round(a.precision_like * m.n_detections), caught = Math.round(a.recall_like * m.n_reference);
    box.replaceChildren(node('p', `On the held-out south half, ${agree} of ${m.n_detections} detections matched a GLAD-L alert (precision-like ${a.precision_like.toFixed(3)}), and ${caught} of ${m.n_reference} GLAD-L events of 1 ha or more were caught (recall-like ${a.recall_like.toFixed(3)}).${d ? ` Its ${d.threshold_db.toFixed(1)} dB threshold was the lowest tested and close to the ${d.stable_forest_noise_sd_db.join('–')} dB noise on stable forest.` : ''}`));
    const hl = m.hand_labeled, hc = el('hand-check');
    if (hl && Number.isFinite(hl.precision) && Number.isFinite(hl.n_sample) && Number.isFinite(hl.n_unsure)) {
      const usable = hl.n_sample - hl.n_unsure, cleared = Math.round(hl.precision * usable);
      hc.textContent = `Hand check: ${cleared} of ${usable} checkable held-out flags showed clearing in Sentinel-2 (${hl.n_unsure} of ${hl.n_sample} had no clear image). Our AI assistant labelled these without seeing the answer key. A re-label by an independent person is still to come.`;
    } else hc.textContent = 'Hand check: pending (metrics.json hand_labeled).';
    if (d) el('detector-intro').textContent = `The first method flagged a change when HH rose or HV fell by ${d.threshold_db.toFixed(1)} dB against earlier passes. It didn't work (see the validation section). By pixel area ${d.detections_on_hansen_intact_pct.south}% (south) to ${d.detections_on_hansen_intact_pct.north}% (north) of its detections were on Hansen-intact forest, and the optical check couldn't tell them apart from undisturbed forest. We left it here for the record.`;
  }

  function limits() {
    const pd = H.frame?.scores?.a_forest_map?.per_date, ds = pd && Object.keys(pd).sort();
    if (!ds?.length) return;
    const f = pd[ds[0]], l = pd[ds[ds.length - 1]];
    el('lim-seasonal').textContent = `Flags compare the last two passes with the first three, so many are likely seasonal drying rather than clearing. Over the full frame the single-pass forest map agrees with Hansen ${pc(f.oa)} on ${ds[0]} but ${pc(l.oa)} on ${ds[ds.length - 1]}, against an all-forest baseline of ${pc(l.all_forest_baseline)}. Late in the dry season, forest just looks less like forest to the radar.`;
  }

  function story() {
    const big = H.big?.scores?.forest_map_vs_hansen, fr = H.frame?.scores, fm = fr?.a_forest_map?.median, gl = fr?.b_alerts?.['GLAD-L'];
    const hd = H.head, ho = hd?.fnf_holdout_20km?.value, ro = hd?.rondonia_transfer?.value, gp = hd?.glad_l_on_prior_clearing?.value, d = hd?.detector?.value;
    const sc = H.cloud?.scenes, cl = Array.isArray(sc) ? sc.filter(s => s.clear_fraction_aoi < 0.02).length : null, np = H.cloud?.nisar_passes?.length;
    const cats = H.big?.lost_categories?.patches, m = metrics;
    const p = (title, text, src) => { const n = node('p', ''); n.append(node('b', title), document.createTextNode(text)); if (src) n.append(node('span', ` (${src})`, 'note')); return n; };
    const pd = fr?.a_forest_map?.per_date, ds = pd && Object.keys(pd).sort();
    fill('story', [
      p('1. The Next Frontier: a place and a sensor.', `The forest edge along the BR-163 highway near Novo Progresso, Pará, where forest is being cut for cattle pasture. NISAR's L-band radar watches it through the cloud. All ${np ?? 'n/a'} passes from June to October were usable. Over the same dry-season months Sentinel-2 had ${cl ?? 'n/a'} fully clouded scenes out of ${sc?.length ?? 'n/a'}, and saw the area well the rest of the time.`, 'submission/sources.md; big/cloud.json'),
      p('2. Radar maps forest well, and the threshold carries over.', `We picked one HV threshold and never refit it. It agrees with the Hansen forest map on ${pc(ho?.oa)} of held-out blocks in the 20 km window (all-forest baseline ${pc(ho?.all_forest_baseline)}), ${pc(ro?.oa)} in Rondônia (${pc(ro?.all_forest_baseline)}), ${pc(big?.oa)} over 60 km (${pc(big?.all_forest_baseline)}) and ${pc(fm?.oa)} over the full frame (${pc(fm?.all_forest_baseline)}).`, 'headline.json, big.json, frame.json'),
      p('3. Forest-to-non-forest flags point at real alerts, but most are unconfirmed.', `Flagged blocks over the full frame are ${times(gl?.lost?.precision_like, gl?.control?.precision_like)} more likely than random stable forest to overlap a GLAD-L alert, but only ${pc(gl?.lost?.precision_like)} of them actually do.${cats ? ` On the 60 km map ${int(cats.radar_only_unconfirmed?.patches)} of ${int(cats.radar_only_unconfirmed?.patches + cats.alert_supported?.patches)} flagged patches have no alert at all.` : ''}${ds ? ` The map's agreement falls from ${pc(pd[ds[0]].oa)} on the first pass to ${pc(pd[ds[ds.length - 1]].oa)} on the last, so many flags are likely seasonal drying.` : ''}`, 'frame.json, big.json'),
      p('4. Our first detector failed, and why.', m?.agreement ? `A 1 dB change detector on the 20 km window matched ${Math.round(m.agreement.precision_like * m.n_detections)} of ${m.n_detections} held-out detections to GLAD-L alerts and caught ${Math.round(m.agreement.recall_like * m.n_reference)} of ${m.n_reference} alert events.${d ? ` Its threshold sat close to the ${d.stable_forest_noise_sd_db.join('–')} dB per-pass noise on stable forest.` : ''}` : 'Pending (metrics.json).', 'data/metrics.json; validation/results_final.md'),
      p('5. Most new alerts are not in old-growth forest.', gp ? `${gp.share_pct}% of 2026 GLAD-L alert pixels in the 20 km window (${int(gp.on_hansen_loss_2001_2025)} of ${int(gp.alert_pixels)}) fall on land Hansen had already mapped as cleared in 2001–2025. That's old pasture being cleared again, and a forest-only method leaves it out on purpose.` : 'Pending (headline.json).', 'validation/results_final.md'),
      p('6. What would fix it.', 'Passes from the wet season and from more than one year, so seasonal drying can be told apart from clearing. A correction for the seasons. A method that knows about pasture and watches it get cleared again. And labels from independent people instead of our AI check.'),
    ]);
  }

  Promise.all([json('data/explore/explore.json'),json('data/detections.geojson'),json('data/summary.json'),json('data/metrics.json'),
    json('data/explore/headline.json'),json('data/explore/big/big.json'),json('data/explore/frame/frame.json'),json('data/explore/big/cloud.json')]).then(([m,d,s,met,hd,bg,fr,cl]) => {
    Object.assign(H, {head: hd, big: bg, frame: fr, cloud: cl});
    if (m?.locations?.length) {
      manifest = m; el('compare-loc').replaceChildren(...m.locations.map(l => new Option(l.name,l.id))); el('compare-loc').disabled = false; compare();
      const para = m.locations.find(l=>l.id==='spara'); if (para) el('patch-date').append(...para.dates.map(date=>new Option(date,date)));
    } else { el('compare-status').textContent = 'Acquisition catalog not available. Restore data/explore/explore.json.'; el('compare-layer').disabled = true; }
    detections = Array.isArray(d?.features) && d.features.every(f=>f?.geometry && f?.properties && Number.isInteger(f.properties.id) && /^\d{4}-\d{2}-\d{2}$/.test(f.properties.first_date) && ['early','late'].includes(f.properties.stage)) ? d : null;
    summary = s; metrics = met; renderPatches(); analysis();
    if (met) { el('metrics-notes').textContent = met.notes || ''; el('download-report').disabled = false; }
    for (const f of [facts, scales, validation, detector, limits, story]) { try { f(); } catch (e) { console.warn(f.name, e); } }
  }).catch(() => { el('compare-status').textContent = 'Data unavailable. Check your connection and reload.'; });
})();
