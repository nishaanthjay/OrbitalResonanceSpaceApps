# Plain-language rules for Amazon Forest Watch

The site is for the general public: no science background, about a 13-year-old reading level.
Every number, every meaning and every honesty caveat stays exactly as it is. Only the words change.

App name: **Through the Clouds** (primary). Secondary line: **Amazon Forest Watch**. Use these exact words.

## Style rules

1. Short sentences: 20 words or fewer. One idea per sentence.
2. Everyday words. Say "radar echo", not "backscatter". Say "photo", not "optical scene".
3. Active voice. "We tested the map", not "The map was tested".
4. Say "you" where it is natural: "Click a patch to see its history."
5. Explain the idea in plain words in the main text. The exact technical term goes only:
   - in a small "?" tooltip (`Glossary.tip('key')`, see below), or
   - in the Glossary drawer, or
   - on a chart axis (e.g. "dB"), or
   - in a source citation / file name (e.g. "NISAR L2 GCOV", `validation/PREREG_frame.md`).
6. Numbers never change. They are still read from the data files at runtime. Add plain context next to them:
   "95.4% agreement, versus 81.3% if you just guessed 'forest' everywhere".
7. Honesty stays, in plain words:
   - Flags are "possible clearing, not confirmed". Never "deforestation" or "forest loss" for a flag.
   - Enrichment (e.g. 25.7x) is never accuracy. Always say "this is not accuracy" nearby.
   - Say "agrees with another map", never "accurate" or "correct".
   - Hansen and GLAD are "other maps to compare with, not ground truth" ("not the final word").
   - Keep: "We don't claim this stops deforestation, saves carbon, or works everywhere."
   - Keep "likely seasonal drying" and "dry season only" warnings.
8. Dates: keep the format the page already uses (2026-06-26 or "June to October"). Don't invent new dates.
9. No hype words ("revolutionary", "powerful", "cutting-edge"). No exclamation marks.
10. Labels and buttons: 1 to 4 plain words ("Map", "Over time", "Spots to check").
11. Do not change ids, classes, data attributes, numbers, file paths, or code logic. Text only.

## The tooltip and glossary component (web/glossary.js + web/glossary.css)

`glossary.js` loads before every other script and defines `window.Glossary`. It holds the one list of terms (the table below, same keys).

- In HTML: `<button type="button" class="tip" data-tip="hv">?</button>` right after the plain word.
  The aria-label ("What does 'tree signal' mean?") is filled in automatically.
- In JS that builds HTML strings: `${Glossary.tip('hv')}`.
- In JS that builds DOM nodes: `node.append(Glossary.tipEl('hv'))`.
- To open the glossary drawer: any element with `data-open-glossary` (optionally `data-open-glossary="hv"` to jump to a term).
- Works by mouse (hover), touch (tap to open, tap elsewhere to close) and keyboard (Tab to the "?", Enter/Space toggles, Esc closes).
  The open tooltip is linked with `aria-describedby`.
- If a key is missing, `Glossary.tip()` returns an empty string, so nothing breaks. Add new terms to `glossary.js` AND this table.

## Glossary (use exactly these plain words)

| key | Technical term | Plain words in the main text | Tooltip (1-2 sentences) |
|---|---|---|---|
| `hv` | HV | tree signal | How strongly the radar bounces back from leaves and branches. Bright = trees. (Radar sent and received sideways: "HV".) |
| `hh` | HH | ground signal | How strongly the radar bounces back from the ground and tree trunks. (Radar sent and received flat: "HH".) |
| `backscatter` | backscatter | radar echo | The part of the radar signal that bounces back to the satellite. Strong echo = bright on the map. |
| `lband` | L-band radar | long-wave radar that passes through clouds | Radar with waves about 24 cm long. Clouds and smoke don't block it, and it reaches into the tree canopy. |
| `db` | dB (decibel) | (chart axes only) | A scale for signal strength. Lower = weaker echo. |
| `nisar` | NISAR | a new NASA-ISRO radar satellite | Launched in 2025 by NASA and India's space agency ISRO. It passes over the same place every 12 days. |
| `pass` | pass / acquisition | pass (one satellite visit) | One time the satellite flew over and took a radar image. |
| `sentinel2` | Sentinel-2 | European photo satellite | A European satellite that takes regular colour photos of the ground. Cloud blocks it. |
| `hansen` | Hansen forest map (Global Forest Change) | another forest map, made from satellite photos | A widely used forest map made from satellite photos, up to 2025. We compare with it, but it is not the final word. |
| `glad` | GLAD alerts (GLAD-L, GLAD-S2) | deforestation alerts | Deforestation alerts from another satellite system, made from photos (GLAD-L from Landsat, GLAD-S2 from Sentinel-2). |
| `firms` | FIRMS / VIIRS | NASA fire detections | NASA's fire detections from space. Each one marks a hot spot about 375 m across. |
| `agreement` | agreement / overall accuracy (OA) | how often our map agrees with the Hansen map | The share of squares where our map and the Hansen map say the same thing. It is agreement with another map, not proof we are right. |
| `baseline` | all-forest baseline | just guessing "forest" everywhere | What you'd get by just guessing "forest" for every square. A useful map has to beat this. |
| `kappa` | kappa | agreement score that removes lucky guesses | 1 = perfect, 0 = no better than chance. |
| `precision` | precision (precision-like) | when we say it, how often the other map says it too | Of all the spots we marked, the share the other map marks the same way. |
| `recall` | recall (recall-like) | how much of it we found | Of all the spots the other map marks, the share we marked too. |
| `holdout` | holdout / out-of-sample | tested on an area the method had never seen | We set the method up on one area, then tested it, unchanged, on a different area. |
| `prereg` | pre-registered | we wrote the rules down before looking at the results | So we couldn't tweak the test after seeing how it went. |
| `flag` | class-switch flag (forest-to-non-forest switch) | possible clearing | A spot that looked like forest early on and like open land at the end. Not confirmed. |
| `enrichment` | enrichment (e.g. 25.7x) | times more likely than random forest to match an alert | How much more often our possible clearings match a real deforestation alert than random patches of forest do. This is not accuracy. |
| `threshold` | threshold | brightness cut-off | The brightness cut-off we use to call a spot forest. Brighter tree signal = forest. |
| `swath` | swath | the strip the satellite sees | The strip of ground the satellite sees on one pass. Outside it, there is no data. |
| `block` | 100 m block | square (100 m on each side, about one hectare) | A square 100 m on each side, about one hectare (a bit more than a football pitch). |
| `hectare` | ha (hectare) | hectare | 100 m x 100 m, a bit bigger than a football pitch. |
| `dryseason` | dry season | dry season (June to October, when there's less cloud) | In this part of the Amazon, June to October has less rain and cloud. We only have data from these months. |
| `jjfast` | JJ-FAST | a Japanese radar method for spotting forest clearing | A forest-clearing warning system from Japan (JAXA/JICA) that uses the same kind of radar. Our first method copied its idea. |
| `gcov` | NISAR L2 GCOV (provisional) | NISAR's early-release radar images | The radar image product we used. "Provisional" means it is an early release that may still change. |
| `gamma0` | gamma0 | radar echo brightness | The radar echo brightness, corrected for the slope of the ground. |
| `speckle` | speckle | radar grain | Random grainy noise that every radar image has. It can make a single spot look brighter or darker. |
| `composite` | composite (R = HH, G = HV, B = HH−HV) | colour mix of the two signals | Red = ground signal, green = tree signal, blue = the difference between them. Forest looks green. |
| `change` | change layer (this pass minus the average of earlier passes) | what changed | How much the echo went up or down compared with the average of all earlier passes. Blue = weaker, red = stronger. |
| `median` | 9-pass median | the typical map over all 9 passes | For each square, the middle value of all 9 passes. It smooths out one-off changes. |
| `confidence` | confidence band (±0.5 dB of the threshold) | unsure squares | Squares whose echo is very close to the cut-off, so they could go either way. |
| `persistence` | passes seen as forest | how many passes it looked like forest | 0 to 9: how many of the 9 passes showed this square as forest. |
| `stable` | stable radar forest | forest that didn't change | Forest far from any clearing, shown as a dashed line so you can compare. |
| `early` | early stage (HH rise) | early sign: ground signal goes up | When trees are first cut, the ground signal often goes up for a while. |
| `late` | late stage (HV drop) | later sign: tree signal goes down | Once trees are gone, the tree signal goes down. |
| `alertsupported` | alert-supported | matches an alert | A possible clearing that overlaps a deforestation alert from another system. Still not checked on the ground. |
| `radaronly` | radar only, unconfirmed | radar only | A possible clearing that no other system has flagged. Not confirmed. |
| `funai` | FUNAI Terras Indígenas / MMA CNUC | Indigenous lands / protected areas | Official boundaries of Indigenous lands (FUNAI) and conservation areas (MMA CNUC) in Brazil. |
| `frame` | frame (track 2, frame 174) | the whole area of one radar image | One full radar image as NISAR delivers it, about 300 km across. |
| `window` | 20 km test window | the 20 km test area | The small area where we first built and tuned the method. It is left out of the bigger scores. |
| `groundtruth` | ground truth | checked on the ground | Information from people who actually went there. We don't have any. |
| `basemap` | Esri basemap | background photo map | A photo map under the radar for orientation. It has no date, so it may be older. |
| `stretch` | display stretch / clipping | brightness range | The fixed brightness range used to draw every image. Values beyond it look the same as the edge. |
| `scene` | scene classification / clear share | share of the photo that's cloud-free | Sentinel-2 marks each pixel as cloud or clear. The clear share is the cloud-free part of the area. |
| `imerg` | GPM IMERG | NASA rainfall data | NASA's satellite rainfall estimates, about 10 km per square. |
| `smap` | SMAP | NASA soil-moisture data | NASA's soil-moisture estimates, about 9 km per square. Partly computed by a model. |

## Terms that may stay in the main text

- Place names: Amazon, Novo Progresso, Pará, BR-163, Rondônia, Brazil.
- Satellite and data names, always with plain words or a "?" next to them the first time in a section: NISAR, Sentinel-2, Hansen, GLAD, FIRMS.
- "dB" only on chart axes and legends of charts.
- File names and source citations.
