// cinema.js : the cinematic layer over explore.js (globe fly-in, 3D, frontier clock, optical vs radar, threat board,
// next-pass countdown, tour). Presentation only: every number and pixel is read from web/data/explore/ files;
// a file that is missing shows "pending". Uses explore.js globals (map, state, go, selectLoc, setMode, fit, ...).
'use strict';
(() => {
  const body = document.body, DAY = 864e5;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const wide = () => innerWidth > 900;
  const node = (tag, text, cls) => mk(tag, text, cls);
  let tour = null; // the running tour's cancel token

  // ================= 1. globe fly-in =================
  // Plays once per tab session, never with reduced motion or when the page is opened on a section link.
  let played = false;
  try { played = sessionStorage.getItem('cine-played') === '1'; } catch { /* storage blocked: play */ }
  const deepLink = location.hash && location.hash !== '#explore';
  const cine = { on: !reduced && !played && !deepLink, spin: 0, cancelled: false };
  map.on('style.load', () => {
    if (reduced) return;
    try {
      map.setProjection({ type: 'globe' });
      map.setSky({ 'sky-color': '#0b1a12', 'horizon-color': '#2a4a38', 'fog-color': '#091008', 'sky-horizon-blend': 0.6,
        'horizon-fog-blend': 0.5, 'fog-ground-blend': 0.6, 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] });
    } catch (e) { console.warn('globe not available', e); }
  });
  const START = () => ({ center: [-12, -6], zoom: wide() ? 1.55 : 0.9, pitch: 0, bearing: 0 });
  if (cine.on) { state.cinema = true; body.classList.add('cine'); map.jumpTo(START()); }

  function setPlace(eyebrow, name) {
    $('cine-eyebrow').textContent = eyebrow;
    const h = $('cine-name');
    h.textContent = name;
    if (!reduced) h.animate([{ opacity: 0, transform: 'translateY(12px)', filter: 'blur(6px)' }, { opacity: 1, transform: 'none', filter: 'none' }], { duration: 700, easing: 'cubic-bezier(.22,1,.36,1)' });
  }
  function spin() { // slow westward drift while the data loads
    let last = performance.now();
    const step = (t) => {
      if (!cine.spin) return;
      const c = map.getCenter();
      map.jumpTo({ center: [c.lng - (t - last) * 0.006, c.lat] });
      last = t;
      cine.spin = requestAnimationFrame(step);
    };
    cine.spin = requestAnimationFrame(step);
  }
  function stopSpin() { cancelAnimationFrame(cine.spin); cine.spin = 0; }
  const fly = (opts) => new Promise((res) => {
    if (cine.cancelled) return res();
    map.once('moveend', res);
    map.flyTo({ ...opts, essential: true });
  });
  const radarIds = ['radarA', 'radarB', 'chgA', 'chgB'];
  function hideRadar() { radarIds.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', 'none')); }
  function fadeRadarIn() { // own ramp: a pending cross-fade in explore.js can not pop the radar in early
    const ids = radarIds.filter((id) => map.getLayer(id)), op = +$('opacity').value / 100, front = slots.radar.front;
    ids.forEach((id) => { map.setPaintProperty(id, 'raster-opacity-transition', { duration: 0, delay: 0 }); map.setPaintProperty(id, 'raster-opacity', 0); map.setLayoutProperty(id, 'visibility', 'visible'); });
    const t0 = performance.now(), D = reduced ? 0 : 1800;
    const step = (t) => {
      const k = D ? Math.min(1, (t - t0) / D) : 1;
      map.setPaintProperty(front, 'raster-opacity', op * easeInOut(k));
      if (k < 1) return requestAnimationFrame(step);
      ids.forEach((id) => map.setPaintProperty(id, 'raster-opacity-transition', { duration: reduced ? 0 : FADE, delay: 0 }));
      setImage(false);
    };
    requestAnimationFrame(step);
  }
  function land() { // hand the camera back to explore.js and fade the radar in under the hero
    stopSpin();
    state.cinema = false;
    body.classList.remove('cine');
    try { sessionStorage.setItem('cine-played', '1'); } catch { /* fine */ }
    if (state.loc) fadeRadarIn();
  }
  async function flyIn() {
    cine.cancelled = false;
    state.cinema = true; body.classList.add('cine');
    hideRadar();
    setPlace('NISAR · L-band radar', 'Earth');
    await sleep(900);
    stopSpin();
    setPlace('South America', 'The Amazon');
    await fly({ center: [-60, -5], zoom: wide() ? 3.3 : 2.4, duration: 3000, curve: 1.2 });
    if (cine.cancelled) return;
    setPlace('Pará, Brazil', 'BR-163 highway');
    await fly({ center: [-55.1, -7.4], zoom: wide() ? 6.6 : 5.6, duration: 2800, curve: 1.3 });
    if (cine.cancelled) return;
    setPlace('Novo Progresso', 'The forest frontier');
    state.cinema = false; // fit() is explore.js's own landing camera
    const done = new Promise((res) => map.once('moveend', res));
    fit(2600);
    await done;
    if (!cine.cancelled) land();
  }
  function skip() {
    if (!state.cinema) return;
    cine.cancelled = true;
    stopSpin();
    map.stop();
    land();
    fit(reduced ? 0 : 700);
  }
  $('cine-skip').onclick = skip;
  ['wheel', 'pointerdown', 'touchstart'].forEach((ev) => $('map').addEventListener(ev, () => { if (state.cinema && !tour) skip(); }, { passive: true, capture: true }));
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.cinema && !tour) skip(); });
  if (cine.on) map.once('load', spin);
  document.addEventListener('explore:ready', () => { if (cine.on && state.cinema) flyIn(); }, { once: true });

  // ================= 2. 3D: terrain + lost patches as columns =================
  const TERRAIN_ATTR = 'Terrain: <a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener">Mapzen / AWS Terrain Tiles</a>';
  const three = { on: false };
  class Ctl3D {
    onAdd() {
      const d = document.createElement('div');
      d.className = 'maplibregl-ctrl maplibregl-ctrl-group';
      d.innerHTML = '<button type="button" class="ctl-3d" aria-pressed="false" title="Tilt the map in 3D (terrain and flagged-patch columns)">3D</button>';
      d.firstChild.onclick = () => set3D(!three.on);
      return d;
    }
    onRemove() {}
  }
  map.addControl(new Ctl3D(), 'top-right');
  function ensure3DLayers() {
    if (!map.getSource('dem')) map.addSource('dem', { type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], encoding: 'terrarium', tileSize: 256, maxzoom: 13, attribution: TERRAIN_ATTR });
    if (!map.getLayer('lost-3d') && map.getSource('lostp') && state.bigMeta && state.bigMeta.first_switch) {
      const pairs = Object.entries(state.bigMeta.first_switch.legend).flat();
      map.addLayer({ id: 'lost-3d', type: 'fill-extrusion', source: 'lostp', layout: { visibility: 'none' }, paint: {
        'fill-extrusion-color': ['match', ['coalesce', ['get', 'first_switch_date'], ''], ...pairs, '#b4401c'],
        'fill-extrusion-height': ['+', 100, ['*', ['get', 'area_ha'], 90]], // height = patch area (37 ha -> ~3.4 km)
        'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.9 } });
      $('legend-3d-ramp').replaceChildren(...Object.entries(state.bigMeta.first_switch.legend).map(([d, c]) => {
        const s = node('span', d.slice(5)); s.style.setProperty('--c', c); return s;
      }));
    }
  }
  function sync3D() {
    const show = three.on && state.mode === 'exploring' && isBig() && $('t-lost').checked;
    if (map.getLayer('lost-3d')) map.setLayoutProperty('lost-3d', 'visibility', show ? 'visible' : 'none');
    $('legend-3d').hidden = !show;
  }
  function set3D(on, duration = 1400) {
    if (on === three.on) return;
    three.on = on;
    document.querySelector('.ctl-3d').setAttribute('aria-pressed', String(on));
    if (on) {
      ensure3DLayers();
      try { map.setTerrain({ source: 'dem', exaggeration: 3 }); } catch (e) { console.warn('terrain not available', e); }
      map.easeTo({ pitch: 62, bearing: map.getBearing() || -18, duration: reduced ? 0 : duration });
    } else {
      map.setTerrain(null);
      map.easeTo({ pitch: 0, bearing: 0, duration: reduced ? 0 : duration });
    }
    sync3D();
  }
  map.on('moveend', sync3D);
  $('t-lost').addEventListener('change', sync3D);
  new MutationObserver(() => { // back to the intro: flatten at once, then let fit() glide to the hero view
    if (state.mode !== 'exploring' && three.on) { set3D(false, 0); fit(); }
    sync3D();
  }).observe(body, { attributes: true, attributeFilter: ['class'] });

  // ================= shared: the 9 per-pass 60 km forest maps, decoded once =================
  let passes = null, passesP = null; // { dates, imgs, share[], valid9 }
  function loadImg(src) {
    return new Promise((res, rej) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => res(im); im.onerror = rej; im.src = src; });
  }
  function loadPasses() { return passesP || (passesP = decodePasses()); }
  async function decodePasses() {
    const meta = state.bigMeta;
    if (!meta || !meta.layers || !Array.isArray(meta.layers.forest)) return null;
    const imgs = await Promise.all(meta.layers.forest.map((f) => loadImg(`${BIG}${f}`)));
    const w = meta.grid.width, h = meta.grid.height, cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    const forest = imgs.map((im) => {
      ctx.clearRect(0, 0, w, h); ctx.drawImage(im, 0, 0);
      const px = ctx.getImageData(0, 0, w, h).data, cls = new Uint8Array(w * h); // 0 no data, 1 forest, 2 non-forest
      for (let k = 0, p = 0; k < cls.length; k++, p += 4) if (px[p + 3] > 0) cls[k] = px[p + 1] > px[p] ? 1 : 2;
      return cls;
    });
    let valid9 = 0;
    const nForest = forest.map(() => 0);
    for (let k = 0; k < w * h; k++) {
      if (forest.some((c) => c[k] === 0)) continue;
      valid9++;
      forest.forEach((c, i) => { if (c[k] === 1) nForest[i]++; });
    }
    passes = { dates: meta.dates, imgs, valid9, share: nForest.map((n) => n / valid9) };
    return passes;
  }
  const big = () => new Promise((res) => { // explore.js loads big.json during map load
    if (state.bigMeta) return res(state.bigMeta);
    document.addEventListener('explore:ready', () => res(state.bigMeta), { once: true });
  });

  // ================= 3. frontier clock =================
  const clock = { i: 0, timer: null };
  function clockShow(i) {
    if (!passes) return;
    clock.i = (i + passes.dates.length) % passes.dates.length;
    const d = passes.dates[clock.i];
    $('clock-imgs').querySelectorAll('img').forEach((im, k) => im.classList.toggle('on', k === clock.i));
    $('clock-date').textContent = `${d} · pass ${clock.i + 1} of ${passes.dates.length}`;
    $('clock-share').textContent = pct(passes.share[clock.i]);
    $('clock-steps').querySelectorAll('button').forEach((b, k) => b.setAttribute('aria-pressed', String(k === clock.i)));
    const cur = $('clock-spark').querySelector('.cur'), pt = $('clock-spark').querySelectorAll('circle')[clock.i];
    if (cur && pt) { cur.setAttribute('x1', pt.getAttribute('cx')); cur.setAttribute('x2', pt.getAttribute('cx')); }
    $('clock-spark').querySelectorAll('circle').forEach((c, k) => c.classList.toggle('on', k === clock.i));
  }
  function clockStop() {
    clearInterval(clock.timer); clock.timer = null;
    $('clock-play').setAttribute('aria-pressed', 'false');
    $('clock-play-txt').textContent = 'Play the clock';
    $('clock-ico').innerHTML = PLAY;
  }
  function clockPlay() {
    if (clock.timer || !passes) return;
    $('clock-play').setAttribute('aria-pressed', 'true');
    $('clock-play-txt').textContent = 'Pause';
    $('clock-ico').innerHTML = PAUSE;
    clockShow(clock.i + 1);
    clock.timer = setInterval(() => clockShow(clock.i + 1), 900);
  }
  function sparkline(share, dates) {
    const W = 320, H = 120, ml = 44, mr = 8, mt = 14, mb = 22;
    const lo = Math.min(...share), hi = Math.max(...share), pad = Math.max((hi - lo) * 0.25, 0.002);
    const t0 = Date.parse(dates[0]), t1 = Date.parse(dates[dates.length - 1]);
    const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr), Y = (v) => mt + (hi + pad - v) / (hi - lo + 2 * pad) * (H - mt - mb);
    const pts = share.map((v, i) => [X(dates[i]), Y(v)]);
    const path = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('');
    const area = `${path}L${pts[pts.length - 1][0]},${H - mb}L${pts[0][0]},${H - mb}Z`;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Forest share on each of the ${dates.length} passes, ${pct(lo)} to ${pct(hi)}">
      <defs><linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#93A889" stop-opacity=".35"/><stop offset="1" stop-color="#93A889" stop-opacity="0"/></linearGradient></defs>
      <path d="${area}" fill="url(#spark-fill)"/><path d="${path}" fill="none" stroke="#93A889" stroke-width="2" stroke-linejoin="round" pathLength="1" class="spark-line"/>
      <line class="cur" x1="${pts[0][0]}" x2="${pts[0][0]}" y1="${mt - 6}" y2="${H - mb}" stroke="#CED9DF" stroke-opacity=".5" stroke-dasharray="2 3"/>
      ${pts.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.5"><title>${dates[i]}: ${pct(share[i])}</title></circle>`).join('')}
      <text x="${ml}" y="${H - 6}" class="lab">${dates[0].slice(5)}</text><text x="${W - mr}" y="${H - 6}" text-anchor="end" class="lab">${dates[dates.length - 1].slice(5)}</text>
      <text x="${ml - 8}" y="${Y(hi) + 4}" text-anchor="end" class="lab">${pct(hi)}</text><text x="${ml - 8}" y="${Y(lo) + 4}" text-anchor="end" class="lab">${pct(lo)}</text></svg>`;
  }
  async function initClock() {
    const meta = await big();
    if (!meta) { $('clock-status').textContent = 'Forest maps pending: web/data/explore/big/ is not available.'; return; }
    let p;
    try { p = await loadPasses(); } catch { p = null; }
    if (!p) { $('clock-status').textContent = 'Forest maps pending: the per-pass layers did not load.'; return; }
    $('clock-imgs').replaceChildren(...p.imgs.map((im, k) => { const c = im.cloneNode(); c.alt = `Forest map from the ${p.dates[k]} pass`; return c; }));
    $('clock-spark').innerHTML = sparkline(p.share, p.dates);
    $('clock-steps').replaceChildren(...p.dates.map((d, k) => {
      const b = node('button', d.slice(5)); b.type = 'button'; b.setAttribute('aria-label', `Pass ${d}`);
      b.onclick = () => { clockStop(); clockShow(k); };
      return b;
    }));
    const min = Math.min(...p.share), max = Math.max(...p.share);
    $('clock-note').textContent = `Share of 100 m blocks classed forest on each pass, among the ${p.valid9.toLocaleString()} display pixels valid on all ${p.dates.length} passes (counted in your browser from the forest_<date>.webp layers). It moves between ${pct(min)} and ${pct(max)}: pass-to-pass swings this size include moisture and speckle, not only clearing, and the dip on the last passes falls in the late dry season, when HV tends to drop as vegetation dries. This is not a forest-loss curve.`;
    $('clock-status').hidden = true;
    $('clock-play').disabled = false;
    clockShow(p.dates.length - 1);
    renderCountdown(meta.dates);
  }
  $('clock-play').onclick = () => (clock.timer ? clockStop() : clockPlay());

  // ================= 6. next-pass countdown (planned 12-day repeat, never a confirmed acquisition) =================
  function nextPlanned(dates) {
    const last = Date.parse(`${dates[dates.length - 1]}T00:00:00Z`), now = new Date();
    const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    let next = last, skipped = 0;
    while (next < today) { next += 12 * DAY; if (next < today) skipped++; }
    return { last: dates[dates.length - 1], next: new Date(next), days: Math.round((next - today) / DAY), skipped };
  }
  function renderCountdown(dates) {
    const n = nextPlanned(dates), when = n.next.toLocaleDateString('en', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
    const inDays = n.days === 0 ? 'today' : n.days === 1 ? 'tomorrow' : `in ${n.days} days`;
    $('countdown').innerHTML = '';
    $('countdown').append(node('span', 'Next pass, planned repeat cycle', 'cd-k'), node('strong', `${when} · ${inDays}`),
      node('small', `Counted in 12-day steps from the last pass in this stack (${n.last}). A planned repeat, not a confirmed acquisition.${n.skipped ? ` ${n.skipped} planned pass${n.skipped > 1 ? 'es' : ''} since then ${n.skipped > 1 ? 'are' : 'is'} not processed here.` : ''} This site does not update itself.`));
    const cap = document.querySelector('.hero .caption');
    if (cap && !cap.querySelector('.cd')) cap.append(node('span', ` · next planned pass ${inDays}`, 'cd'));
  }

  // ================= 4. optical vs radar (web/data/explore/optical/, Max B; "pending" until it exists) =================
  const OPT = `${DATA}optical/`;
  const ovr = { opt: null, cloud: null, i: 0 };
  function optFor(d) { // tolerant reader: {passes:[{nisar_date, file?, scene_id?, date?, cloud_pct?}]} or keyed by date
    const o = ovr.opt;
    if (!o) return null;
    const list = Array.isArray(o) ? o : Array.isArray(o.passes) ? o.passes : Array.isArray(o.items) ? o.items : null;
    const e = list ? list.find((x) => x && x.nisar_date === d) : o[d] || (o.passes && o.passes[d]);
    if (!e) return null;
    const file = e.file || (e.scene_id ? `optical_${d}.webp` : null);
    return { ...e, file };
  }
  function nearestScene(d) {
    const sc = ovr.cloud && ovr.cloud.scenes;
    if (!sc || !sc.length) return null;
    const t = Date.parse(d);
    return sc.reduce((a, b) => (Math.abs(Date.parse(b.date) - t) < Math.abs(Date.parse(a.date) - t) ? b : a));
  }
  function ovrShow(i) {
    const meta = state.bigMeta, d = meta.dates[i];
    ovr.i = i;
    $('ovr-radar').src = `${BIG}${meta.layers.forest[i]}`;
    $('ovr-rad-label').textContent = d;
    const o = optFor(d), cmp = $('ovr');
    const ns = nearestScene(d), gapDays = ns ? Math.round(Math.abs(Date.parse(ns.date) - Date.parse(d)) / DAY) : null;
    if (o && o.file) {
      $('ovr-optical').src = `${OPT}${o.file}`;
      $('ovr-opt-label').textContent = `${o.date || ''}${Number.isFinite(o.cloud_pct) ? ` · ${o.cloud_pct.toFixed(0)}% cloud` : ''}`;
      cmp.classList.remove('no-opt');
      $('ovr-status').hidden = true;
    } else {
      $('ovr-optical').removeAttribute('src');
      cmp.classList.add('no-opt');
      $('ovr-status').hidden = false;
      $('ovr-status').textContent = ovr.opt
        ? `No optical scene within 6 days of ${d}.`
        : `Sentinel-2 image: pending (web/data/explore/optical/ not built yet).${ns ? ` Nearest scene ${ns.date}, ${gapDays} d away, ${pct(ns.clear_fraction_aoi, 0)} of the box clear.` : ''}`;
    }
    $('ovr-passes').querySelectorAll('button').forEach((b, k) => b.setAttribute('aria-pressed', String(k === i)));
    const cur = $('ovr-timeline').querySelector('.cur');
    if (cur) { const x = cur.dataset[`x${i}`]; cur.setAttribute('x1', x); cur.setAttribute('x2', x); }
  }
  function dualTimeline(c, passesD) {
    const W = 560, H = 230, ml = 74, mr = 10, rowR = 30, top = 66, bot = H - 26;
    const t0 = Date.parse(passesD[0]) - 3 * DAY, t1 = Date.parse(passesD[passesD.length - 1]) + 3 * DAY;
    const X = (d) => ml + (Date.parse(d) - t0) / (t1 - t0) * (W - ml - mr), Y = (f) => top + (1 - f) * (bot - top);
    const good = c.good_threshold;
    let g = `<text x="0" y="${rowR + 4}" class="lab">NISAR</text><text x="0" y="${Y(0.45) + 4}" class="lab">Sentinel-2</text><text x="0" y="${Y(0.45) + 17}" class="lab dim">clear share</text>`;
    g += `<line x1="${ml}" x2="${W - mr}" y1="${rowR}" y2="${rowR}" class="axis"/>`;
    for (const f of [0, 1]) g += `<line x1="${ml}" x2="${W - mr}" y1="${Y(f)}" y2="${Y(f)}" class="axis"/><text x="${ml - 6}" y="${Y(f) + 4}" text-anchor="end" class="lab dim">${f * 100}%</text>`;
    g += `<line x1="${ml}" x2="${W - mr}" y1="${Y(good)}" y2="${Y(good)}" stroke="#fdd663" stroke-dasharray="3 3" stroke-opacity=".7"/><text x="${ml - 6}" y="${Y(good) + 4}" text-anchor="end" class="lab" style="fill:#fdd663">${good * 100}%</text>`;
    const xs = passesD.map(X);
    g += `<line class="cur" ${xs.map((x, i) => `data-x${i}="${x.toFixed(1)}"`).join(' ')} x1="${xs[0]}" x2="${xs[0]}" y1="${rowR - 14}" y2="${bot}" stroke="#CED9DF" stroke-opacity=".45" stroke-dasharray="2 3"/>`;
    g += xs.map((x, i) => `<circle cx="${x.toFixed(1)}" cy="${rowR}" r="6" class="rad"><title>NISAR ${passesD[i]}: usable</title></circle>`).join('');
    g += c.scenes.map((s) => `<circle cx="${X(s.date).toFixed(1)}" cy="${Y(s.clear_fraction_aoi).toFixed(1)}" r="4" class="${s.clear_fraction_aoi >= good ? 'opt good' : 'opt'}"><title>Sentinel-2 ${s.date}: ${pct(s.clear_fraction_aoi)} clear</title></circle>`).join('');
    g += [0, Math.floor(passesD.length / 2), passesD.length - 1].map((i) => `<text x="${xs[i]}" y="${H - 6}" text-anchor="middle" class="lab dim">${passesD[i].slice(5)}</text>`).join('');
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="NISAR passes and Sentinel-2 clear share per scene">${g}</svg>`;
  }
  async function initOptical() {
    const meta = await big();
    if (!meta) { $('ovr-status').textContent = 'Radar forest maps pending.'; return; }
    [ovr.opt, ovr.cloud] = await Promise.all([getJSON(`${OPT}optical.json`), getJSON(`${BIG}cloud.json`)]);
    $('ovr-passes').replaceChildren(...meta.dates.map((d, k) => {
      const b = node('button', d.slice(5)); b.type = 'button'; b.setAttribute('aria-label', `Compare on ${d}`);
      b.onclick = () => ovrShow(k);
      return b;
    }));
    const c = ovr.cloud;
    if (c && Array.isArray(c.scenes) && c.scenes.length) {
      $('ovr-timeline').innerHTML = dualTimeline(c, c.nisar_passes || meta.dates);
      const s = c.summary && c.summary.aoi, pd = meta.dates.map((d) => Date.parse(d)), gap = Math.max(...pd.slice(1).map((t, i) => (t - pd[i]) / DAY));
      if (s) $('ovr-summary').replaceChildren(kvList([
        ['NISAR passes usable', `${meta.dates.length} of ${meta.dates.length} · longest gap ${gap} days`],
        ['Sentinel-2 scenes at least 80% clear', `${int(s.n_ge_80pct_clear)} of ${int(s.n_scenes)} · longest gap ${s.longest_gap_days_between_good_views} days`],
        ['Median clear share per Sentinel-2 scene', pct(s.median_clear_fraction)],
      ]));
      $('ovr-note').textContent = 'June to October is the dry season here, and Sentinel-2 saw this box well: optical does not go blind in this window. What radar adds is that no pass is lost to cloud, so every 12-day map is usable without screening. The wet season (about November to May), when cloud is heavier, was not measured. Clear shares come from Sentinel-2 scene classification, which misses haze and small clouds. Source: big/cloud.json.';
    } else $('ovr-timeline').replaceChildren(node('span', 'pending', 'tag'));
    ovrShow(meta.dates.length - 1);
  }
  $('ovr-swipe').oninput = (e) => $('ovr').style.setProperty('--split', `${e.target.value}%`);

  // ================= 5. threat board =================
  const tl = { k: 0, timer: null, cards: [] };
  function cropFor(p, meta) { // 3.2 km square around a patch centroid, in display-grid pixels
    const [a, , c, , e, f] = meta.grid.transform, [mx, my] = merc(p.centroid_lon, p.centroid_lat);
    const S = 32, cx = (mx - c) / a, cy = (my - f) / e;
    return { sx: Math.round(cx - S / 2), sy: Math.round(cy - S / 2), S, toPx: (lon, lat) => { const [x, y] = merc(lon, lat); return [(x - c) / a, (y - f) / e]; } };
  }
  function drawCard(card, k) {
    const { ctx, crop, ring, color, W } = card, sc = W / crop.S;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#0e1a10'; ctx.fillRect(0, 0, W, W);
    ctx.drawImage(passes.imgs[k], crop.sx, crop.sy, crop.S, crop.S, 0, 0, W, W);
    if (ring) {
      ctx.strokeStyle = color; ctx.lineWidth = 1.5 * devicePixelRatio; ctx.beginPath();
      ring.forEach(([x, y], i) => { const px = (x - crop.sx) * sc, py = (y - crop.sy) * sc; if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); });
      ctx.closePath(); ctx.stroke();
    }
  }
  function tlStep(k) {
    if (!passes) return;
    tl.k = (k + passes.dates.length) % passes.dates.length;
    tl.cards.forEach((c) => drawCard(c, tl.k));
    $('tl-date').textContent = `${passes.dates[tl.k]} · pass ${tl.k + 1} of ${passes.dates.length}`;
  }
  async function initThreats() {
    const meta = await big();
    const pj = await getJSON(`${BIG}big_protected.json`);
    const areas = $('threat-areas');
    areas.replaceChildren();
    if (pj && Array.isArray(pj.areas)) {
      const rows = [...pj.areas].sort((x, y) => y.lost_ha_inside - x.lost_ha_inside);
      const o = pj.outside_all_areas || {}, max = Math.max(...rows.map((r) => r.lost_share_of_valid_blocks), o.lost_share_of_valid_blocks || 0);
      const row = (name, sub, val, share, cls) => {
        const r = node('div', undefined, `threat-row ${cls || ''}`), bar = node('span', undefined, 'tbar');
        bar.style.setProperty('--w', `${(100 * share / max).toFixed(1)}%`);
        const t = node('div'); t.append(node('b', name), node('small', sub));
        r.append(t, node('strong', val), bar);
        return r;
      };
      rows.forEach((a, i) => areas.append(row(`${i + 1}. ${a.name}`, `${a.kind.split(' (')[0]} · ${a.etnia_nome || ''}`.replace(/ · $/, ''), `${int(a.lost_blocks_inside)} ha`, a.lost_share_of_valid_blocks)));
      if (o.lost_blocks != null) areas.append(row('Outside all protected areas', 'for comparison', `${int(o.lost_blocks)} ha`, o.lost_share_of_valid_blocks, 'ref'));
      areas.append(node('p', `Bar = share of the area's mapped 100 m blocks flagged forest-to-cleared June to October (${rows.map((a) => `${a.name} ${pct(a.lost_share_of_valid_blocks)}`).join(', ')}; outside ${pct(o.lost_share_of_valid_blocks)}). Whole 60 km map, test window included; a block counts when its centre is inside the official FUNAI boundary. MMA CNUC lists no conservation unit in this box. Flags are unconfirmed radar change, and some are likely seasonal drying.`, 'note'));
    } else areas.append(node('span', 'pending', 'tag'));

    const box = $('threat-clusters');
    const wp = meta && meta.watch_priorities;
    if (!wp || !Array.isArray(wp.items)) { box.replaceChildren(node('span', 'pending', 'tag')); return; }
    let p = null;
    try { p = await loadPasses(); } catch { p = null; }
    box.replaceChildren();
    tl.cards = [];
    wp.items.forEach((it, rank) => {
      const b = node('button', undefined, 'cluster'); b.type = 'button';
      b.setAttribute('aria-label', `Fly to patch ${it.id}, ${it.area_ha} hectares`);
      const W = 84 * devicePixelRatio, cv = document.createElement('canvas');
      cv.width = W; cv.height = W; cv.setAttribute('aria-hidden', 'true');
      const txt = node('span', undefined, 'cl-txt');
      txt.append(node('b', `${it.area_ha} ha`), node('span', `${it.category === 'alert_supported' ? 'alert-supported' : 'radar only, unconfirmed'}`, it.category === 'alert_supported' ? 'cat al' : 'cat ro'),
        node('small', `non-forest from ${it.first_switch_date.slice(5)} · ${int(it.distance_m)} m from cleared land${it.in_original_window ? ' · test window' : ''}`));
      b.append(node('i', String(rank + 1), 'rank'), cv, txt, node('span', 'Fly there', 'fly'));
      b.onclick = () => { toTop(); openLost(it.id); };
      box.append(b);
      if (p) {
        const f = state.lost && state.lost.byId.get(it.id), crop = cropFor(it, meta);
        const ring = f && f.geometry.type === 'Polygon' ? f.geometry.coordinates[0].map(([lon, lat]) => crop.toPx(lon, lat)) : null;
        tl.cards.push({ ctx: cv.getContext('2d'), crop, ring, W, color: it.category === 'alert_supported' ? '#fdd663' : '#f3b49b' });
      }
    });
    if (p) {
      tlStep(p.dates.length - 1);
      if (!reduced && 'IntersectionObserver' in window) {
        new IntersectionObserver((es) => es.forEach((e) => {
          clearInterval(tl.timer); tl.timer = null;
          if (e.isIntersecting) tl.timer = setInterval(() => tlStep(tl.k + 1), 700);
        })).observe(box);
      }
    } else $('tl-date').textContent = 'Time-lapse pending: the per-pass forest maps did not load.';
  }

  // ================= 7. tour mode (~60 s, for the screen recording) =================
  function caption(text, step, n) {
    $('tour-text').textContent = text;
    $('tour-step').textContent = `${step} / ${n}`;
    if (!reduced) $('tour-text').animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 450, easing: 'cubic-bezier(.22,1,.36,1)' });
  }
  async function wait(ms, tok) {
    const t0 = performance.now();
    while (performance.now() - t0 < ms) { if (tok.stop) throw new Error('tour stopped'); await sleep(Math.min(120, ms)); }
  }
  function playPasses(on) { if (on && !state.playing) $('play').click(); if (!on) stopPlay(); }
  function scrollToId(id) { document.getElementById(id).scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' }); }
  async function runTour() {
    if (tour) return endTour();
    const meta = state.bigMeta, fm = meta && meta.scores && meta.scores.forest_map_vs_hansen, fr = state.frameMeta;
    const top = meta && meta.watch_priorities && meta.watch_priorities.items && meta.watch_priorities.items[0];
    const tok = { stop: false };
    tour = tok;
    body.classList.add('touring');
    $('tour-btn').setAttribute('aria-pressed', 'true');
    $('tour').hidden = false;
    const steps = [
      async () => {
        caption('NISAR, the NASA-ISRO L-band radar, maps this Amazon frontier every 12 days, cloud or not.', 1, 8);
        toTop(); setMode('intro'); set3D(false, 0);
        if (!reduced) { map.jumpTo(START()); spin(); await flyIn(); } else await wait(4000, tok);
        await wait(1200, tok);
      },
      async () => {
        caption('The 20 km test window, radar composite: 9 passes from June to October 2026.', 2, 8);
        await go('composite'); await wait(1200, tok); playPasses(true); await wait(6500, tok); playPasses(false);
      },
      async () => {
        if (!meta) return;
        caption(`60 km, out of sample: one fixed threshold. The forest map agrees with Hansen on ${pct(fm && fm.oa)} of blocks, against ${pct(fm && fm.all_forest_baseline)} for "all forest". A reference, not ground truth.`, 3, 8);
        await go('big'); state.layer = 'forest';
        document.querySelectorAll('input[name=layer]').forEach((r) => { r.checked = r.value === 'forest'; });
        setImage(); await wait(1400, tok); playPasses(true); await wait(6500, tok); playPasses(false);
      },
      async () => {
        if (!meta) return;
        caption('Blocks flagged as switching from forest to non-forest rise as columns: height is patch area, colour is the pass they first switched. Unconfirmed radar change.', 4, 8);
        set3D(true, 2000); await wait(2200, tok);
        if (!reduced) map.easeTo({ bearing: map.getBearing() + 70, duration: 6500, easing: (t) => t });
        await wait(6800, tok); set3D(false, 1200); await wait(1300, tok);
      },
      async () => {
        if (!top) return;
        caption(`Place to check first: ${top.area_ha} ha, ${top.category === 'alert_supported' ? 'with a GLAD alert' : 'radar only, unconfirmed'}, non-forest from ${top.first_switch_date}. A flag to check, not confirmed clearing.`, 5, 8);
        await openLost(top.id); await wait(7000, tok);
      },
      async () => {
        if (!fr) return;
        const f = fr.scores && fr.scores.a_forest_map && fr.scores.a_forest_map.median, km = fr.scores && fr.scores.blocks && fr.scores.blocks.scored_km2;
        caption(`The whole radar frame: ${km ? `${Math.round(km).toLocaleString()} km²` : 'scored area'} scored once, ${pct(f && f.oa)} agreement with Hansen against ${pct(f && f.all_forest_baseline)} for "all forest".`, 6, 8);
        await go('frame'); await wait(7000, tok);
      },
      async () => {
        caption('The frontier clock: the 60 km forest map redrawn from each pass, with its forest share.', 7, 8);
        setMode('intro'); await wait(300, tok); scrollToId('frontier'); await wait(1200, tok);
        clockStop(); clockShow(0); clockPlay(); await wait(7200, tok); clockStop();
      },
      async () => {
        caption('Where to look first: flagged blocks inside Indigenous lands and the largest flagged patches, pass by pass. It does not stop deforestation; it shows where to check.', 8, 8);
        scrollToId('threats'); await wait(8000, tok);
      },
    ];
    try {
      for (const s of steps) { if (tok.stop) break; await s(); }
    } catch { /* stopped */ }
    if (tour === tok) endTour(true);
  }
  function endTour(finished) {
    const tok = tour;
    if (!tok) return;
    tok.stop = true; tour = null;
    if (state.cinema) skip();
    playPasses(false); clockStop();
    if (three.on) set3D(false, 600);
    body.classList.remove('touring');
    $('tour-btn').setAttribute('aria-pressed', 'false');
    $('tour').hidden = true;
    if (finished) { toTop(); setMode('intro'); }
  }
  $('tour-btn').onclick = runTour;
  $('tour-stop').onclick = () => endTour();
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && tour) endTour(); });

  initClock();
  initOptical();
  initThreats();
})();
