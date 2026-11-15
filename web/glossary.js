// glossary.js : Amazon Forest Watch. One list of plain-language terms (mirrors web/tools/PLAIN_LANGUAGE.md),
// a small "?" tooltip that works by mouse, touch and keyboard, and a Glossary drawer. Text only; no data or numbers.
(() => {
  'use strict';
  const TERMS = {
    hv: {"term": "HV", "plain": "tree signal", "tip": "How strongly the radar bounces back from leaves and branches. Bright = trees. (Radar sent and received sideways: \"HV\".)"},
    hh: {"term": "HH", "plain": "ground signal", "tip": "How strongly the radar bounces back from the ground and tree trunks. (Radar sent and received flat: \"HH\".)"},
    backscatter: {"term": "backscatter", "plain": "radar echo", "tip": "The part of the radar signal that bounces back to the satellite. Strong echo = bright on the map."},
    lband: {"term": "L-band radar", "plain": "long-wave radar that passes through clouds", "tip": "Radar with waves about 24 cm long. Clouds and smoke don't block it, and it reaches into the tree canopy."},
    db: {"term": "dB (decibel)", "plain": "(chart axes only)", "tip": "A scale for signal strength. Lower = weaker echo."},
    nisar: {"term": "NISAR", "plain": "a new NASA-ISRO radar satellite", "tip": "Launched in 2025 by NASA and India's space agency ISRO. It passes over the same place every 12 days."},
    pass: {"term": "pass / acquisition", "plain": "pass (one satellite visit)", "tip": "One time the satellite flew over and took a radar image."},
    sentinel2: {"term": "Sentinel-2", "plain": "European photo satellite", "tip": "A European satellite that takes regular colour photos of the ground. Cloud blocks it."},
    hansen: {"term": "Hansen forest map (Global Forest Change)", "plain": "another forest map, made from satellite photos", "tip": "A widely used forest map made from satellite photos, up to 2025. We compare with it, but it is not the final word."},
    glad: {"term": "GLAD alerts (GLAD-L, GLAD-S2)", "plain": "deforestation alerts", "tip": "Deforestation alerts from another satellite system, made from photos (GLAD-L from Landsat, GLAD-S2 from Sentinel-2)."},
    firms: {"term": "FIRMS / VIIRS", "plain": "NASA fire detections", "tip": "NASA's fire detections from space. Each one marks a hot spot about 375 m across."},
    agreement: {"term": "agreement / overall accuracy (OA)", "plain": "how often our map agrees with the Hansen map", "tip": "The share of squares where our map and the Hansen map say the same thing. It is agreement with another map, not proof we are right."},
    baseline: {"term": "all-forest baseline", "plain": "just guessing \"forest\" everywhere", "tip": "What you'd get by just guessing \"forest\" for every square. A useful map has to beat this."},
    kappa: {"term": "kappa", "plain": "agreement score that removes lucky guesses", "tip": "1 = perfect, 0 = no better than chance."},
    precision: {"term": "precision (precision-like)", "plain": "when we say it, how often the other map says it too", "tip": "Of all the spots we marked, the share the other map marks the same way."},
    recall: {"term": "recall (recall-like)", "plain": "how much of it we found", "tip": "Of all the spots the other map marks, the share we marked too."},
    holdout: {"term": "holdout / out-of-sample", "plain": "tested on an area the method had never seen", "tip": "We set the method up on one area, then tested it, unchanged, on a different area."},
    prereg: {"term": "pre-registered", "plain": "we wrote the rules down before looking at the results", "tip": "So we couldn't tweak the test after seeing how it went."},
    flag: {"term": "class-switch flag (forest-to-non-forest switch)", "plain": "possible clearing", "tip": "A spot that looked like forest early on and like open land at the end. Not confirmed."},
    enrichment: {"term": "enrichment (e.g. 25.7x)", "plain": "times more likely than random forest to match an alert", "tip": "How much more often our possible clearings match a real deforestation alert than random patches of forest do. This is not accuracy."},
    threshold: {"term": "threshold", "plain": "brightness cut-off", "tip": "The brightness cut-off we use to call a spot forest. Brighter tree signal = forest."},
    swath: {"term": "swath", "plain": "the strip the satellite sees", "tip": "The strip of ground the satellite sees on one pass. Outside it, there is no data."},
    block: {"term": "100 m block", "plain": "square (100 m on each side, about one hectare)", "tip": "A square 100 m on each side, about one hectare (a bit more than a football pitch)."},
    hectare: {"term": "ha (hectare)", "plain": "hectare", "tip": "100 m x 100 m, a bit bigger than a football pitch."},
    dryseason: {"term": "dry season", "plain": "dry season (June to October, when there's less cloud)", "tip": "In this part of the Amazon, June to October has less rain and cloud. We only have data from these months."},
    jjfast: {"term": "JJ-FAST", "plain": "a Japanese radar method for spotting forest clearing", "tip": "A forest-clearing warning system from Japan (JAXA/JICA) that uses the same kind of radar. Our first method copied its idea."},
    gcov: {"term": "NISAR L2 GCOV (provisional)", "plain": "NISAR's early-release radar images", "tip": "The radar image product we used. \"Provisional\" means it is an early release that may still change."},
    gamma0: {"term": "gamma0", "plain": "radar echo brightness", "tip": "The radar echo brightness, corrected for the slope of the ground."},
    speckle: {"term": "speckle", "plain": "radar grain", "tip": "Random grainy noise that every radar image has. It can make a single spot look brighter or darker."},
    composite: {"term": "composite (R = HH, G = HV, B = HH−HV)", "plain": "colour mix of the two signals", "tip": "Red = ground signal, green = tree signal, blue = the difference between them. Forest looks green."},
    change: {"term": "change layer (this pass minus the average of earlier passes)", "plain": "what changed", "tip": "How much the echo went up or down compared with the average of all earlier passes. Blue = weaker, red = stronger."},
    median: {"term": "9-pass median", "plain": "the typical map over all 9 passes", "tip": "For each square, the middle value of all 9 passes. It smooths out one-off changes."},
    confidence: {"term": "confidence band (±0.5 dB of the threshold)", "plain": "unsure squares", "tip": "Squares whose echo is very close to the cut-off, so they could go either way."},
    persistence: {"term": "passes seen as forest", "plain": "how many passes it looked like forest", "tip": "0 to 9: how many of the 9 passes showed this square as forest."},
    stable: {"term": "stable radar forest", "plain": "forest that didn't change", "tip": "Forest far from any clearing, shown as a dashed line so you can compare."},
    early: {"term": "early stage (HH rise)", "plain": "early sign: ground signal goes up", "tip": "When trees are first cut, the ground signal often goes up for a while."},
    late: {"term": "late stage (HV drop)", "plain": "later sign: tree signal goes down", "tip": "Once trees are gone, the tree signal goes down."},
    alertsupported: {"term": "alert-supported", "plain": "matches an alert", "tip": "A possible clearing that overlaps a deforestation alert from another system. Still not checked on the ground."},
    radaronly: {"term": "radar only, unconfirmed", "plain": "radar only", "tip": "A possible clearing that no other system has flagged. Not confirmed."},
    funai: {"term": "FUNAI Terras Indígenas / MMA CNUC", "plain": "Indigenous lands / protected areas", "tip": "Official boundaries of Indigenous lands (FUNAI) and conservation areas (MMA CNUC) in Brazil."},
    frame: {"term": "frame (track 2, frame 174)", "plain": "the whole area of one radar image", "tip": "One full radar image as NISAR delivers it, about 300 km across."},
    window: {"term": "20 km test window", "plain": "the 20 km test area", "tip": "The small area where we first built and tuned the method. It is left out of the bigger scores."},
    groundtruth: {"term": "ground truth", "plain": "checked on the ground", "tip": "Information from people who actually went there. We don't have any."},
    basemap: {"term": "Esri basemap", "plain": "background photo map", "tip": "A photo map under the radar for orientation. It has no date, so it may be older."},
    stretch: {"term": "display stretch / clipping", "plain": "brightness range", "tip": "The fixed brightness range used to draw every image. Values beyond it look the same as the edge."},
    scene: {"term": "scene classification / clear share", "plain": "share of the photo that's cloud-free", "tip": "Sentinel-2 marks each pixel as cloud or clear. The clear share is the cloud-free part of the area."},
    imerg: {"term": "GPM IMERG", "plain": "NASA rainfall data", "tip": "NASA's satellite rainfall estimates, about 10 km per square."},
    smap: {"term": "SMAP", "plain": "NASA soil-moisture data", "tip": "NASA's soil-moisture estimates, about 9 km per square. Partly computed by a model."}
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const label = (k) => `What does "${TERMS[k].plain.replace(/\s*\(.*\)$/, '')}" mean?`;
  const tip = (k) => TERMS[k] ? `<button type="button" class="tip" data-tip="${k}" aria-label="${esc(label(k))}">?</button>` : '';
  const tipEl = (k) => {
    if (!TERMS[k]) return document.createTextNode('');
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tip'; b.dataset.tip = k; b.setAttribute('aria-label', label(k)); b.textContent = '?';
    return b;
  };

  // ---- one shared bubble, linked by aria-describedby while open ----
  let bubble = null, owner = null, pinned = false;
  function ensureBubble() {
    if (bubble) return bubble;
    bubble = document.createElement('div');
    bubble.id = 'tip-bubble'; bubble.className = 'tip-bubble'; bubble.setAttribute('role', 'tooltip'); bubble.hidden = true;
    document.body.append(bubble);
    return bubble;
  }
  function place(btn) {
    const r = btn.getBoundingClientRect(), b = bubble.getBoundingClientRect(), pad = 8, vw = document.documentElement.clientWidth;
    let left = r.left + r.width / 2 - b.width / 2;
    left = Math.max(pad, Math.min(left, vw - b.width - pad));
    let top = r.bottom + 8;
    if (top + b.height > window.innerHeight - pad && r.top - b.height - 8 > pad) top = r.top - b.height - 8;
    bubble.style.left = `${Math.round(left)}px`; bubble.style.top = `${Math.round(top)}px`;
  }
  function show(btn, pin) {
    const t = TERMS[btn.dataset.tip]; if (!t) return;
    ensureBubble();
    if (owner && owner !== btn) owner.removeAttribute('aria-describedby'), owner.setAttribute('aria-expanded', 'false');
    owner = btn; pinned = !!pin;
    bubble.innerHTML = `<b>${esc(t.term)}</b><span>${esc(t.tip)}</span><a href="#" data-open-glossary="${btn.dataset.tip}">Glossary</a>`;
    bubble.hidden = false; place(btn);
    btn.setAttribute('aria-describedby', 'tip-bubble'); btn.setAttribute('aria-expanded', 'true');
  }
  function hide() {
    if (!bubble || bubble.hidden) return;
    bubble.hidden = true; pinned = false;
    if (owner) { owner.removeAttribute('aria-describedby'); owner.setAttribute('aria-expanded', 'false'); }
    owner = null;
  }
  const isTip = (el) => el && el.closest && el.closest('.tip[data-tip]');
  document.addEventListener('mouseover', (e) => { const b = isTip(e.target); if (b && !pinned) show(b, false); });
  document.addEventListener('mouseout', (e) => {
    const b = isTip(e.target); if (!b || pinned) return;
    if (e.relatedTarget && (b.contains(e.relatedTarget) || (bubble && bubble.contains(e.relatedTarget)))) return;
    hide();
  });
  document.addEventListener('focusin', (e) => { const b = isTip(e.target); if (b) show(b, false); });
  document.addEventListener('focusout', (e) => { const b = isTip(e.target); if (b && !pinned && !(bubble && bubble.contains(e.relatedTarget))) hide(); });
  document.addEventListener('click', (e) => {
    const b = isTip(e.target);
    if (b) { e.preventDefault(); e.stopPropagation(); if (owner === b && pinned) hide(); else show(b, true); return; }
    const g = e.target.closest && e.target.closest('[data-open-glossary]');
    if (g) { e.preventDefault(); hide(); openGlossary(g.dataset.openGlossary || ''); return; }
    if (bubble && !bubble.hidden && !bubble.contains(e.target)) hide();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && bubble && !bubble.hidden) { const o = owner; hide(); o && o.focus(); } });
  window.addEventListener('scroll', () => { if (owner && bubble && !bubble.hidden) place(owner); }, { passive: true, capture: true });
  window.addEventListener('resize', () => { if (owner && bubble && !bubble.hidden) place(owner); });

  // ---- glossary drawer ----
  let drawer = null;
  function buildDrawer() {
    if (drawer) return drawer;
    drawer = document.createElement('dialog');
    drawer.id = 'glossary'; drawer.className = 'glossary'; drawer.setAttribute('aria-labelledby', 'glossary-title');
    const items = Object.entries(TERMS).sort((a, b) => a[1].plain.localeCompare(b[1].plain))
      .map(([k, t]) => `<div class="g-item" id="g-${k}" tabindex="-1"><dt>${esc(t.plain)}</dt><dd><span class="g-term">${esc(t.term)}</span>${esc(t.tip)}</dd></div>`).join('');
    drawer.innerHTML = `<header><h2 id="glossary-title">Glossary</h2><button type="button" class="mini" data-close-glossary>Close</button></header>
      <p class="note">Plain words used on this site, the technical term behind each one, and what it means.</p><dl>${items}</dl>`;
    drawer.addEventListener('click', (e) => { if (e.target === drawer || e.target.closest('[data-close-glossary]')) drawer.close(); });
    document.body.append(drawer);
    return drawer;
  }
  function openGlossary(k) {
    const d = buildDrawer();
    if (!d.open) { try { d.showModal(); } catch (_) { d.setAttribute('open', ''); } }
    d.querySelectorAll('.g-item.on').forEach((n) => n.classList.remove('on'));
    const item = k && d.querySelector(`#g-${CSS.escape(k)}`);
    if (item) { item.classList.add('on'); item.scrollIntoView({ block: 'center' }); item.focus({ preventScroll: true }); }
    else d.querySelector('[data-close-glossary]').focus();
  }

  // fill in aria-labels for "?" buttons written directly in HTML
  function decorate(root) {
    (root.querySelectorAll ? root : document).querySelectorAll('.tip[data-tip]:not([aria-label])').forEach((b) => {
      if (TERMS[b.dataset.tip]) b.setAttribute('aria-label', label(b.dataset.tip));
      if (b.tagName === 'BUTTON' && !b.type) b.type = 'button';
    });
  }
  const start = () => { decorate(document); new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 && decorate(n)))).observe(document.body, { childList: true, subtree: true }); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  window.Glossary = { terms: TERMS, tip, tipEl, open: openGlossary, plain: (k) => (TERMS[k] ? TERMS[k].plain : '') };
})();
