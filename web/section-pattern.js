// section-pattern.js : Amazon Forest Watch. Shared helpers for the TAKEAWAY / VISUAL / "How we know" pattern
// (web/tools/SECTION_PATTERN.md). Presentation only: every number passed in is read from data files by the caller.
(() => {
  'use strict';
  const fin = (x) => typeof x === 'number' && Number.isFinite(x);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---- number style: rounded in main text, exact only inside "How we know" ----
  const outOf100 = (f) => (fin(f) ? `${Math.round(f * 100)} out of 100` : 'not available');       // 0.954 -> "95 out of 100"
  const pct = (f) => (fin(f) ? `${Math.round(f * 100)}%` : 'not available');                       // 0.954 -> "95%"
  const exactPct = (f, d = 1) => (fin(f) ? `${(f * 100).toFixed(d)}%` : 'not available');          // 0.954 -> "95.4%" (How we know only)
  const times = (x) => (fin(x) ? `about ${Math.round(x)} times` : 'not available');                // 25.7 -> "about 26 times"
  const count = (n) => (fin(n) ? Math.round(n).toLocaleString('en-US') : 'not available');          // 57117.4 -> "57,117"
  const about = (n, step = 1000) => (fin(n) ? `about ${(Math.round(n / step) * step).toLocaleString('en-US')}` : 'not available'); // 57117 -> "about 57,000"

  // ---- comparison bar with direct labels ----
  // bar([{ value: 0.954, label: 'Our map', tone: 'forest' }, { value: 0.813, label: "Guessing 'forest' everywhere", tone: 'muted' }], { max: 1, format: pct })
  // tones: forest (green), cleared (orange), alert (cyan), spot (yellow), muted (grey)
  function bar(rows, opt = {}) {
    const max = opt.max ?? Math.max(...rows.map((r) => (fin(r.value) ? r.value : 0)), 1e-9);
    const format = opt.format || pct;
    const wrap = document.createElement('div');
    wrap.className = 'sp-bars';
    if (opt.label) wrap.setAttribute('aria-label', opt.label);
    wrap.setAttribute('role', 'img');
    const said = [];
    for (const r of rows) {
      const row = document.createElement('div');
      row.className = `sp-bar sp-${r.tone || 'forest'}`;
      const w = fin(r.value) ? Math.max(0, Math.min(1, r.value / max)) * 100 : 0;
      const shown = r.text ?? format(r.value);
      row.innerHTML = `<span class="sp-bar-label">${esc(r.label)}</span><span class="sp-bar-track"><span class="sp-bar-fill" style="width:${w.toFixed(1)}%"></span></span><span class="sp-bar-value">${esc(shown)}</span>`;
      wrap.append(row);
      said.push(`${r.label}: ${shown}`);
    }
    if (!opt.label) wrap.setAttribute('aria-label', said.join('; '));
    return wrap;
  }

  // ---- "How we know" details, collapsed by default ----
  // how(nodeOrHtml, { summary }) -> <details class="sp-how">; pass a DOM node, an array of nodes, or an HTML string you built from fixed text + numbers
  function how(content, opt = {}) {
    const d = document.createElement('details');
    d.className = 'sp-how';
    const s = document.createElement('summary');
    s.textContent = opt.summary || 'How we know';
    const body = document.createElement('div');
    body.className = 'sp-how-body';
    if (typeof content === 'string') body.innerHTML = content;
    else [].concat(content).forEach((n) => n && body.append(n));
    d.append(s, body);
    return d;
  }

  // ---- short link to the single site-wide limits box ----
  const limitsLink = (text = "See what this can't tell you") => `<a class="sp-limits-link" href="#limits">${esc(text)}</a>`;

  // set a takeaway line (plain text) and keep it readable by screen readers as the section summary
  function takeaway(id, text) { const n = document.getElementById(id); if (n) n.textContent = text; return n; }

  window.SP = { outOf100, pct, exactPct, times, count, about, bar, how, limitsLink, takeaway, esc };
})();
