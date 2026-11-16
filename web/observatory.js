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
    // pick the section that passed the line most recently (robust even if nav order and page order ever differ)
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

  // in-page links (top bar, footer, "How it works"...): land the target just under the fixed header, and correct
  // once scrolling settles, because images above the target can still load and push the page during the scroll
  const headerGap = () => (document.querySelector('.top')?.getBoundingClientRect().bottom || 64) + 20;
  let jumpToken = 0;
  const jumpTo = (target) => {
    const token = ++jumpToken;
    const want = () => Math.round(target.getBoundingClientRect().top + scrollY - headerGap());
    const maxY = () => document.documentElement.scrollHeight - innerHeight;
    scrollTo({ top: want(), behavior: reduced ? 'auto' : 'smooth' });
    let tries = 0, last = -1, still = 0;
    const settle = () => {
      if (token !== jumpToken) return;
      if (Math.abs(scrollY - last) > 1) { last = scrollY; still = 0; return setTimeout(settle, 120); }
      if (++still < 2) return setTimeout(settle, 120); // scrolling has stopped for ~240 ms
      const y = Math.min(want(), maxY());
      if (Math.abs(scrollY - y) > 4 && tries++ < 4) { last = -1; still = 0; scrollTo({ top: y, behavior: 'auto' }); setTimeout(settle, 200); }
    };
    setTimeout(settle, 200);
  };
  addEventListener('wheel', () => jumpToken++, { passive: true }); addEventListener('touchstart', () => jumpToken++, { passive: true }); // the visitor took over
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('a[href^="#"]:not([data-go])');
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const href = a.getAttribute('href'); if (href.length < 2) return;
    const target = document.getElementById(decodeURIComponent(href.slice(1))); if (!target) return;
    e.preventDefault(); history.pushState(null, '', href); jumpTo(target);
    if (!target.hasAttribute('tabindex') && !/^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(target.tagName)) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });

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
    if (!before || !after || before >= after) { status.hidden = false; status.textContent = 'Pick a Before date that is earlier than the After date.'; el('swipe').disabled = true; return; }
    status.hidden = false; status.textContent = 'Loading the two radar images…'; el('swipe').disabled = true;
    el('compare-note').textContent = layer.endsWith('chg') ? `Change preview: each pass compared with the average of its own earlier passes. It is not simply After minus Before. Blue = weaker echo, red = stronger; scale ±${manifest.change_range_db} dB. Changes under 1 dB are see-through. The preview is made from the map images, which are cut off at the brightness limits.` : `${loc.name}. ${layer === 'composite' ? 'Colour mix: red = ground signal (HH), green = tree signal (HV), blue = the difference (HH−HV).' : `${layer === 'hv' ? 'Tree signal' : 'Ground signal'} (${layer.toUpperCase()}) radar echo brightness: ${loc.stretch[layer].lo} to ${loc.stretch[layer].hi} dB.`} Both dates use the same brightness range and the same area. See-through spots have no data.`;
    try {
      const loaded = await Promise.all([before,after].map(date => new Promise((resolve,reject) => { const img = new Image(); const timer = setTimeout(() => reject(new Error('Image load timed out')),15000); img.onload = () => { clearTimeout(timer); resolve(img); }; img.onerror = () => { clearTimeout(timer); reject(new Error('Image not available')); }; img.src = imagePath(loc,layer,date); })));
      if (version !== compareVersion) return;
      ['before-image','after-image'].forEach((id,i) => { el(id).src = loaded[i].src; el(id).alt = `${loc.name}, ${layer}, ${[before,after][i]}, NISAR radar`; el(id).hidden = false; });
      status.hidden = true; el('swipe').disabled = false;
    } catch { if (version !== compareVersion) return; status.textContent = 'No images for this pair. Try another date or radar view.'; }
  }
  el('compare-loc').onchange = () => { el('before-date').replaceChildren(); el('after-date').replaceChildren(); compare(); };
  el('compare-layer').onchange = compare;
  ['before-date','after-date'].forEach(id => el(id).onchange = updateComparison);
  el('swipe').oninput = e => el('comparison').style.setProperty('--split', `${e.target.value}%`);

  let detections = null, summary = null, metrics = null, openPatch = null;
  function renderPatches() {
    const box = el('patches'); box.replaceChildren();
    if (!detections) { el('patch-count').textContent = 'Patch data not available. Restore data/detections.geojson to look at patches.'; return; }
    const stage = el('patch-stage').value, date = el('patch-date').value;
    const features = detections.features.filter(f => (stage === 'all' || f.properties.stage === stage) && (date === 'all' || f.properties.first_date <= date));
    el('patch-count').textContent = `${features.length} patches · all parts of the area · first seen by the date you picked`;
    if (!features.length) box.append(node('p','No patches match these choices.','note'));
    features.forEach(f => {
      const p = f.properties, button = node('button','', 'patch'); button.type = 'button';
      if (p.id === openPatch) button.setAttribute('aria-current', 'true');
      const label = node('span', `Patch ${p.id}`); label.append(node('small',`${p.first_date} · ${p.split ? ({tune:'setup half', holdout:'test half', buffer:'strip between halves'}[p.split] || p.split) : 'Part not available'}`));
      const detail = node('span', `${fmt(p.area_ha)} ha`, p.stage); detail.append(node('small',p.stage === 'early' ? 'Early · ground signal up' : 'Late · tree signal down'));
      button.append(label,detail); button.onclick = async () => {
        if (!manifest || typeof state === 'undefined' || !state.manifest || !map.getSource('radarA')) { el('patch-count').textContent = 'The map is not ready yet. Wait a moment and try again.'; return; }
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
    const rows = [['Patches on the map',features?.length,'Joined across dates · whole test area'],['Total patch area',total === null ? null : `${fmt(total)} ha`,'All patches added up · possible change, not confirmed'],['Early-sign patches',features?.filter(f => f.properties.stage === 'early').length,'Ground signal went up · whole test area'],['Later-sign patches',features?.filter(f => f.properties.stage === 'late').length,'Tree signal went down · whole test area']];
    rows.forEach(([title,value,note]) => { const card = node('article','', 'metric'); card.append(node('span',title),node('strong',value == null ? 'Not available' : typeof value === 'number' ? fmt(value) : value),node('small',note)); box.append(card); });
    countUp(box);
    const chart = el('area-chart'); chart.replaceChildren();
    const rowsData = summary?.per_date;
    if (!Array.isArray(rowsData) || !rowsData.length || !rowsData.every(r => typeof r.date === 'string' && ['total_area_ha','early_ha','late_ha'].every(k => Number.isFinite(r[k]) && r[k] >= 0))) { chart.append(node('p','Per-date area data not available.','note')); return; }
    const max = Math.max(...rowsData.map(r => r.total_area_ha),1);
    rowsData.forEach(r => {
      const row = node('div','', 'bar-row'); row.setAttribute('aria-label',`${r.date}: ${r.total_area_ha} hectares; early sign ${r.early_ha}; later sign ${r.late_ha}`);
      const track = node('div','', 'bar-track');
      for (const [key,cls] of [['early_ha',''],['late_ha','late']]) { const bar = node('span','',`bar-segment ${cls}`); bar.style.width = `${100*r[key]/max}%`; track.append(bar); }
      row.append(node('span',r.date.slice(5)),track,node('span',`${fmt(r.total_area_ha)} ha`,'bar-value')); chart.append(row);
    });
    chart.append(node('p','Sage: early sign (HH up) · Blue-gray: later sign (HV down)','note'));
    const details = document.createElement('details'), caption = node('summary','Show as a table'), table = document.createElement('table');
    const head = document.createElement('tr'); ['Date','Patches','Area (ha)','Early sign (ha)','Later sign (ha)'].forEach(t => head.append(node('th',t))); table.append(head);
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
    const report = {title:'Through the Clouds · Amazon Forest Watch: data report',sources:['data/detections.geojson','data/summary.json','data/metrics.json','data/explore/explore.json'],scope:'Southern Para; map patches span the whole window; agreement is scored only on holdout per-date detections.',caveats:['Radar disturbance is not confirmed deforestation.','GLAD-L alerts are a reference, not ground truth.','The same AI assistant that ran detection also labelled the optical chips. No independent person has checked them.'],map_patch_count:detections?.features.length ?? null,map_patch_area_ha:detections?.features.every(f=>Number.isFinite(f.properties.area_ha)) ? detections.features.reduce((s,f)=>s+f.properties.area_ha,0) : null,summary,metrics};
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
    const g = n => Number.isFinite(n) ? SP.pct(n) : 'n/a';
    const item = (k, big1, vs, txt, tip, exact) => { const a = node('article', '', 'fact'), s = node('small', txt); if (tip) s.append(Glossary.tipEl(tip)); if (exact) a.title = exact; a.append(node('span', k, 'k'), node('strong', big1), node('span', vs, 'vs'), s); return a; };
    const ratio = Number.isFinite(gl?.lost?.precision_like) && Number.isFinite(gl?.control?.precision_like) && gl.control.precision_like > 0 ? SP.times(gl.lost.precision_like / gl.control.precision_like) : 'n/a';
    fill('facts', [
      item('60 km forest map', g(big?.oa), `agrees with the standard map (Hansen). Guessing "forest" everywhere gets ${g(big?.all_forest_baseline)}.`, 'Tested on an area it had never seen.', 'hansen', `Exact: ${pc(big?.oa)} vs ${pc(big?.all_forest_baseline)} guessing. Full figures in How good is it.`),
      item('Whole radar image', g(fm?.oa), `agrees with the standard map. Guessing "forest" gets ${g(fm?.all_forest_baseline)}.`, `About ${Number.isFinite(fr?.blocks?.scored_km2) ? SP.about(fr.blocks.scored_km2, 1000).replace('about ', '') : 'n/a'} km² scored, same settings, tested once.`, 'frame', `Exact: ${pc(fm?.oa)} vs ${pc(fm?.all_forest_baseline)} guessing; kappa ${Number.isFinite(fm?.kappa) ? fm.kappa.toFixed(2) : 'n/a'}; ${int(fr?.blocks?.scored_km2)} km² scored.`),
      item('Possible clearings', ratio, 'more likely than untouched forest to match a deforestation alert (GLAD-L).', 'Not confirmed, so this is not accuracy.', 'flag', `Exact: ${pc(gl?.lost?.precision_like)} vs ${pc(gl?.control?.precision_like, 2)} (${times(gl?.lost?.precision_like, gl?.control?.precision_like)}).`),
      item('Dry season, June to October', np ? `${np} of ${np}` : 'n/a', `radar passes usable. Photo satellite: ${cl ?? 'n/a'} of ${sc?.length ?? 'n/a'} scenes fully hidden by cloud.`, 'The photo satellite still saw this area well most of the time.', 'dryseason', 'Fully hidden = under 2% clear sky (Sentinel-2).'),
    ]);
  }
  // "In 30 seconds" cards: numbers come from big.json at runtime
  function in30() {
    const big = H.big?.scores?.forest_map_vs_hansen, t = el('in30-t2'), box = el('in30-bars');
    if (!t || !box || !Number.isFinite(big?.oa)) return;
    t.textContent = `Its forest map agrees with the standard map about ${Math.round(big.oa * 100)} times out of 100.`;
    box.replaceChildren(SP.bar([
      { value: big.oa, label: 'Our map', tone: 'forest' },
      { value: big.all_forest_baseline, label: 'Guessing "forest" everywhere', tone: 'muted' },
    ], { max: 1, format: SP.pct, label: `Agreement with the standard map: ours ${SP.pct(big.oa)}, guessing forest everywhere ${SP.pct(big.all_forest_baseline)}` }));
  }

  function scales() {
    const hd = H.head, T = hd?.T_db?.value, tb = hd?.tune_blocks?.value;
    // innerHTML only holds fixed text, Glossary tips and formatted numbers
    el('scales-threshold').innerHTML = Number.isFinite(T)
      ? `One brightness cut-off${Glossary.tip('threshold')} for the tree signal${Glossary.tip('hv')} (${T.toFixed(2)} dB), set on a ${Number.isFinite(tb) ? `${int(tb / 100)} km² strip (${int(tb)} squares, ` : ''}the north half of the 20 km test area${Number.isFinite(tb) ? ')' : ''}. We never changed it.`
      : 'Cut-off not loaded yet (headline.json).';
    const rows = [
      ['20 km test area (unseen half)', hd?.fnf_holdout_20km?.value, 'validation/fnf_metrics.json holdout.all'],
      ['Rondônia, 20 km (new area)', hd?.rondonia_transfer?.value, 'validation/fnf_metrics.json transfer_rondonia.all'],
      ['60 km, BR-163 frontier', H.big?.scores?.forest_map_vs_hansen, 'big.json scores.forest_map_vs_hansen'],
      ['Whole radar image', H.frame?.scores?.a_forest_map?.median, 'frame.json scores.a_forest_map.median'],
    ];
    const t = el('scales'); t.replaceChildren();
    const thead = document.createElement('thead'), hr = document.createElement('tr');
    [['Area'], ['Size scored', 'block'], ['Agrees with Hansen', 'agreement'], ["Just guessing 'forest'", 'baseline'], ['Score without lucky guesses', 'kappa'],
     ['Forest: match', 'precision', ' / found', 'recall'], ['Not forest: match', 'precision', ' / found', 'recall']].forEach(([a, k1, b, k2]) => {
      const th = node('th', a); if (k1) th.append(Glossary.tipEl(k1)); if (b) th.append(b, Glossary.tipEl(k2)); hr.append(th);
    });
    thead.append(hr); t.append(thead);
    const tb2 = document.createElement('tbody');
    rows.forEach(([label, c, src]) => {
      const tr = document.createElement('tr'); tr.title = src;
      if (!c) { tr.append(node('td', label), node('td', 'pending')); tb2.append(tr); return; }
      const [np, nr] = nfPR(c);
      [label, `${int(c.n / 100)} km²`, pc(c.oa), pc(c.all_forest_baseline), c.kappa.toFixed(3), `${pc(c.forest_precision)} / ${pc(c.forest_recall)}`, `${pc(np)} / ${pc(nr)}`]
        .forEach((v, i) => tr.append(node(i ? 'td' : 'th', v)));
      tb2.append(tr);
    });
    t.append(tb2);
    el('scales-note').textContent = 'Size = scored squares, 100 m on each side (1 hectare each). "Match" = when we say it, how often Hansen says it too. "Found" = how much of Hansen\'s we found. We worked out the "not forest" values from the same counts. The 60 km row leaves out the 20 km test area. Rondônia is a different area, with the same cut-off. Sources: hover a row, or see validation/results_final.md.';
  }

  function validation() {
    const big = H.big?.scores?.forest_map_vs_hansen, fm = H.frame?.scores?.a_forest_map?.median;
    const gl = H.frame?.scores?.b_alerts?.['GLAD-L'], lp = gl?.lost?.precision_like, cp = gl?.control?.precision_like;
    const small = v => Number.isFinite(v) && v < 0.005 ? 'under 1%' : SP.pct(v); // a share that rounds to 0% reads "under 1%"
    const card = (bigText, lines, bars, label) => { const c = node('article', '', 'sp-card'); c.append(node('span', bigText, 'sp-big')); lines.forEach(l => c.append(l)); c.append(SP.bar(bars, { max: 1, format: SP.pct, label })); return c; };
    const line = (txt, tip) => { const p = node('p', txt); if (tip) p.append(Glossary.tipEl(tip)); return p; };
    const timesBig = Number.isFinite(lp) && Number.isFinite(cp) && cp > 0 ? SP.times(lp / cp) : 'not available';
    fill('val-forest', [
      card(SP.outOf100(big?.oa), [line('Our 60 km map agrees with the standard forest map.', 'agreement')],
        [{ value: big?.oa, label: 'Our map', tone: 'forest' }, { value: big?.all_forest_baseline, label: "Just guessing 'forest' everywhere", tone: 'muted' }], 'Our 60 km map agrees with the Hansen map; compared with guessing forest everywhere'),
      card(SP.outOf100(fm?.oa), [line(`Whole radar image, ${SP.about(H.frame?.scores?.blocks?.scored_km2)} km².`)],
        [{ value: fm?.oa, label: 'Our map', tone: 'forest' }, { value: fm?.all_forest_baseline, label: "Just guessing 'forest' everywhere", tone: 'muted' }], 'Our whole-image map agrees with the Hansen map; compared with guessing forest everywhere'),
      card(timesBig.charAt(0).toUpperCase() + timesBig.slice(1), [line(`Possible clearings are ${timesBig} more likely than random forest to match a real deforestation alert.`, 'enrichment'), line("That means they're not random. It doesn't mean they're right.")],
        [{ value: lp, label: 'Possible clearings with an alert', tone: 'alert', text: small(lp) }, { value: cp, label: 'Random forest with an alert', tone: 'muted', text: small(cp) }], 'Share of possible clearings with a GLAD-L alert, compared with random unchanged forest'),
    ]);
    const sub = el('analysis-sub'); if (sub) sub.innerHTML = `Tested against the Hansen map and GLAD-L alerts. ${SP.limitsLink()}`;
    const t = document.createElement('table'), hr = document.createElement('tr'); t.className = 'sp-table';
    [['Area'], ['Alerts from', 'glad'], ['Possible clearings (squares)', 'flag'], ['With an alert'], ['Random unchanged forest with an alert', 'stable'], ['Times more likely (not accuracy)', 'enrichment']].forEach(([h, k]) => { const th = node('th', h); if (k) th.append(Glossary.tipEl(k)); hr.append(th); });
    t.append(hr);
    for (const [name, al] of [['60 km', H.big?.scores?.alerts], ['Whole radar image', H.frame?.scores?.b_alerts]]) for (const src of ['GLAD-L', 'GLAD-S2']) {
      const a = al?.[src], tr = document.createElement('tr');
      [name, src, int(a?.lost?.n_blocks), pc(a?.lost?.precision_like), pc(a?.control?.precision_like, 2), times(a?.lost?.precision_like, a?.control?.precision_like)].forEach((v, i) => tr.append(node(i ? 'td' : 'th', v)));
      t.append(tr);
    }
    fill('val-enrich', [t]);
  }

  function detector() { // the failed first attempt, from data/metrics.json + headline.json detector
    const m = metrics, d = H.head?.detector?.value, box = el('results');
    if (!m?.agreement || m.agreement.split !== 'holdout') { fill('results', [node('span', 'pending', 'tag')]); return; }
    const a = m.agreement, agree = Math.round(a.precision_like * m.n_detections), caught = Math.round(a.recall_like * m.n_reference);
    const rp = document.createElement('p'); // innerHTML only holds fixed text, Glossary tips and numbers from metrics.json / headline.json
    rp.innerHTML = `We tested it on the south half, which it had never seen${Glossary.tip('holdout')}. ${agree} of ${m.n_detections} spots it flagged matched a GLAD-L alert (match rate ${a.precision_like.toFixed(3)}${Glossary.tip('precision')}). It found ${caught} of ${m.n_reference} GLAD-L alerts of 1 hectare or more (found rate ${a.recall_like.toFixed(3)}${Glossary.tip('recall')}).${d ? ` Its cut-off of ${d.threshold_db.toFixed(1)} dB was the lowest we tried. That is close to the ${d.stable_forest_noise_sd_db.join('–')} dB random wobble of unchanged forest${Glossary.tip('speckle')}.` : ''}`;
    box.replaceChildren(rp);
    const hl = m.hand_labeled, hc = el('hand-check');
    if (hl && Number.isFinite(hl.precision) && Number.isFinite(hl.n_sample) && Number.isFinite(hl.n_unsure)) {
      const usable = hl.n_sample - hl.n_unsure, cleared = Math.round(hl.precision * usable);
      hc.textContent = `Hand check: ${cleared} of ${usable} flags we could check from the unseen half showed clearing in Sentinel-2 photos (${hl.n_unsure} of ${hl.n_sample} had no clear photo). Our AI assistant labelled these without seeing the answer key. An independent human re-label is still pending.`;
    } else hc.textContent = 'Hand check: not loaded yet (metrics.json hand_labeled).';
    if (d) el('detector-intro').innerHTML = `Our first method flagged a change when the ground signal${Glossary.tip('hh')} rose or the tree signal${Glossary.tip('hv')} fell by ${d.threshold_db.toFixed(1)} dB, compared with earlier passes. It didn't work (numbers above). By area, ${d.detections_on_hansen_intact_pct.south}% (south) to ${d.detections_on_hansen_intact_pct.north}% (north) of what it flagged was forest Hansen calls untouched. In the photos, these spots looked just like untouched forest. We kept it here for the record.`;
  }

  function limits() {
    const pd = H.frame?.scores?.a_forest_map?.per_date, ds = pd && Object.keys(pd).sort();
    if (!ds?.length) return;
    const f = pd[ds[0]], l = pd[ds[ds.length - 1]];
    el('lim-seasonal').innerHTML = `Flags compare the last two passes with the first three, so many are likely seasonal drying, not clearing. Over the whole radar image, a one-pass forest map agrees with Hansen about ${SP.outOf100(f.oa)} on the first pass but only ${SP.outOf100(l.oa)} on the last. Just guessing 'forest' gives ${SP.outOf100(l.all_forest_baseline)}. Late in the dry season, forest looks less like forest to the radar.<br><small class="note">Exact: ${pc(f.oa)} on ${ds[0]}, ${pc(l.oa)} on ${ds[ds.length - 1]}; guessing 'forest' ${pc(l.all_forest_baseline)}.</small>`;
  }

  function story() {
    const big = H.big?.scores?.forest_map_vs_hansen, fr = H.frame?.scores, fm = fr?.a_forest_map?.median, gl = fr?.b_alerts?.['GLAD-L'];
    const hd = H.head, ho = hd?.fnf_holdout_20km?.value, ro = hd?.rondonia_transfer?.value, gp = hd?.glad_l_on_prior_clearing?.value, d = hd?.detector?.value;
    const sc = H.cloud?.scenes, cl = Array.isArray(sc) ? sc.filter(s => s.clear_fraction_aoi < 0.02).length : null, np = H.cloud?.nisar_passes?.length;
    const cats = H.big?.lost_categories?.patches, m = metrics;
    const pc = v => SP.pct(v), times = (a, b) => Number.isFinite(a) && Number.isFinite(b) && b > 0 ? SP.times(a / b) : 'n/a'; // main text is rounded; exact values live in How we know
    const p = (title, text, src) => { const n = node('p', ''); n.append(node('b', title), document.createTextNode(text)); if (src) n.append(node('span', ` (${src})`, 'note')); return n; };
    const pd = fr?.a_forest_map?.per_date, ds = pd && Object.keys(pd).sort();
    fill('story', [
      p('1. Through the Clouds: a place and a satellite.',`The forest edge along the BR-163 highway near Novo Progresso, Pará. Here forest is being cut for cattle pasture. NISAR's long-wave radar sees it through cloud. All ${np ?? 'n/a'} passes from June to October were usable. In the same dry-season months, ${cl ?? 'n/a'} of ${sc?.length ?? 'n/a'} Sentinel-2 photos were fully clouded. The rest of the time it saw the area well.`, 'submission/sources.md; big/cloud.json'),
      p('2. Radar maps forest well, and the cut-off works elsewhere too.',`We picked one tree-signal cut-off and never changed it. Here is how often it agrees with the Hansen map, with "just guessing forest" in brackets. Unseen half of the 20 km test area: ${pc(ho?.oa)} (${pc(ho?.all_forest_baseline)}). Rondônia: ${pc(ro?.oa)} (${pc(ro?.all_forest_baseline)}). 60 km: ${pc(big?.oa)} (${pc(big?.all_forest_baseline)}). Whole radar image: ${pc(fm?.oa)} (${pc(fm?.all_forest_baseline)}).`, 'headline.json, big.json, frame.json'),
      p('3. Possible clearings point at real alerts, but most are not confirmed.',`Over the whole radar image, flagged squares are ${times(gl?.lost?.precision_like, gl?.control?.precision_like)} more likely than random unchanged forest to overlap a GLAD-L alert. This is not accuracy: only ${pc(gl?.lost?.precision_like)} of them actually do.${cats ? ` On the 60 km map, ${int(cats.radar_only_unconfirmed?.patches)} of ${int(cats.radar_only_unconfirmed?.patches + cats.alert_supported?.patches)} possible-clearing patches have no alert at all.` : ''}${ds ? ` The map's agreement falls from ${pc(pd[ds[0]].oa)} on the first pass to ${pc(pd[ds[ds.length - 1]].oa)} on the last. So many flags are likely seasonal drying.` : ''}`, 'frame.json, big.json'),
      p('4. Our first detector failed, and why.',m?.agreement ? `A simple change detector (1 dB) on the 20 km test area flagged ${m.n_detections} spots on the unseen half. Only ${Math.round(m.agreement.precision_like * m.n_detections)} matched GLAD-L alerts. It found ${Math.round(m.agreement.recall_like * m.n_reference)} of ${m.n_reference} alerts.${d ? ` Its cut-off sat close to the ${d.stable_forest_noise_sd_db.join('–')} dB random wobble that unchanged forest shows on each pass.` : ''}` : 'Not loaded yet (metrics.json).', 'data/metrics.json; validation/results_final.md'),
      p('5. Most new alerts are not in old-growth forest.',gp ? `${gp.share_pct}% of 2026 GLAD-L alert spots in the 20 km test area (${int(gp.on_hansen_loss_2001_2025)} of ${int(gp.alert_pixels)}) fall on land Hansen had already mapped as cleared in 2001–2025. That's old pasture being cleared again. Our forest-only method leaves it out on purpose.` : 'Not loaded yet (headline.json).', 'validation/results_final.md'),
      p('6. What would fix it.','Radar passes from the wet season and from more than one year, to tell seasonal drying apart from clearing. A fix for seasonal changes. A method that knows about pasture and watches it get cleared again. And labels from independent people instead of our AI check.'),
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
    if (met) { // plain summary on the page; the full technical note from metrics.json stays on hover and in the data report
      const mn = el('metrics-notes'); mn.title = met.notes || '';
      mn.textContent = met.notes ? 'We scored this once, on the unseen south half. We chose the settings on the north half first. Alerts are another map to compare with, not the final word. This is not accuracy. Full record: validation/results_final.md.' : '';
      if (met.notes) { const sm = document.createElement('small'); sm.textContent = ` Technical note: ${met.notes}`; mn.append(sm); }
      el('download-report').disabled = false; }
    for (const f of [facts, in30, scales, validation, detector, limits, story]) { try { f(); } catch (e) { console.warn(f.name, e); } }
  }).catch(() => { el('compare-status').textContent = 'Data unavailable. Check your connection and reload.'; });
})();
