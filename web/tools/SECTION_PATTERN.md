# Section pattern for Amazon Forest Watch

Goal: a member of the public gets each section in 5 seconds. Presentation only: no data, numbers in data,
algorithm or validation results change, no feature is removed, and every honesty caveat still exists somewhere.
Plain words come from `web/tools/PLAIN_LANGUAGE.md` (still the glossary of record).

## Every section has three parts, in this order

1. **TAKEAWAY**: one sentence, at most 18 words, the answer to "so what?". It is the biggest text in the section.
   `<p class="sp-takeaway" id="<section>-takeaway">…</p>` (add class `wide` for longer lines). Optional one-line `<p class="sp-sub">` under it.
   If the sentence holds a number, build it in JS from data (`SP.takeaway(id, text)`), with a sensible static fallback that has no number.
2. **VISUAL**: one chart, map or image with **direct labels on it**. A reader should not need a separate legend.
   Wrap it in `<figure class="sp-visual">`. Use `.sp-callout.forest|cleared|alert|spot` for labels placed on a map/image,
   `SP.bar(rows, opt)` for comparison bars (each bar labels itself), `.sp-swatch.<tone>` for inline colour keys.
3. **"How we know"**: `<details class="sp-how">` collapsed by default (`SP.how(content)` builds one).
   It holds the method, the exact decimals, technical terms, file names and the caveats specific to this section.
   Tables go here as `<div class="sp-table-wrap"><table class="sp-table">`: labels in the first column, values right-aligned, no word-per-line wrapping.

Site-wide caveats live in ONE box, "What this can't tell you" (`#limits`, in the How good is it section). Elsewhere, replace repeated
caveat paragraphs with `SP.limitsLink()` / `<a class="sp-limits-link" href="#limits">See what this can't tell you</a>`.
A caveat that belongs to one section only (e.g. "a fire nearby doesn't prove it caused the change") stays in that section: short in the
main text if it changes how you read the visual, otherwise inside "How we know".

## Number style

- Main text: rounded and plain. "95 out of 100" (`SP.outOf100(0.954)`), whole percents "95%" (`SP.pct`), "about 26 times" (`SP.times(25.7)`),
  "about 57,000 km²" (`SP.about(57117)`), counts with commas (`SP.count`).
- Exact values (95.4%, kappa 0.86, 0.035, 57,117 km²) only inside "How we know" (`SP.exactPct(f, 1)`).
- Data stores shares as fractions (0.954). Never type a number into the page: read it from the data file the section already loads.
- No monospace for numbers in main text (`font-variant-numeric: proportional-nums`). Monospace is fine inside "How we know" tables only if it aligns better; prefer `tabular-nums`.

## Words

- At most one "?" glossary chip per sentence. Prefer explaining in the sentence: "Hansen, the standard global forest map".
- Sentences of 20 words or fewer. Everyday words. "You" where natural.
- Honesty, in plain words: possible clearings are "not confirmed"; "about 26 times more likely… That means they're not random. It doesn't mean they're right.";
  "agrees with the standard map", never "accurate"; Hansen/GLAD are other maps, not the final word.

## Colour language (one meaning everywhere; tokens in `web/section-pattern.css`)

| Meaning | Token | Colour |
|---|---|---|
| Forest | `--c-forest` | green `#5fbf6a` |
| Cleared land, possible clearing | `--c-cleared` | orange `#e8893a` |
| Selected spot | `--c-spot` | yellow `#ffe14d` (white outline also fine) |
| Deforestation alerts | `--c-alert` | cyan `#35d0e0` |
| Comparison / "just guessing" | `--c-muted` | grey `#8f9c94` |

Map image layers are pre-rendered data files and keep their own colours; legends and callouts next to them must name what the colour means.

## Type and contrast

Body 17px, line-height 1.5, lines at most ~70ch. Body text colour `--text-body` (#d3ddd6) and secondary `--text-soft` (#b3c1b8), both above 4.5:1 on the dark background.
Fewer borders and glass; more spacing. Keep keyboard focus, focus outlines and reduced-motion behaviour.

## Helpers (`web/section-pattern.js`, loaded right after `glossary.js`, defines `window.SP`)

| Helper | Use |
|---|---|
| `SP.outOf100(f)`, `SP.pct(f)`, `SP.exactPct(f, d)`, `SP.times(x)`, `SP.count(n)`, `SP.about(n, step)` | number formats above |
| `SP.bar(rows, {max, format, label})` | rows `{value, label, tone, text?}`; returns a labelled bar chart node with an aria-label |
| `SP.how(content, {summary})` | returns a collapsed `<details class="sp-how">`; content = node(s) or an HTML string built from fixed text + numbers |
| `SP.limitsLink(text?)` | HTML string for the link to `#limits` |
| `SP.takeaway(id, text)` | sets a takeaway line's text |
| `SP.esc(s)` | HTML-escape |
