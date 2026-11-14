# Story panel text

Numbers in brackets are citations; the list is at the bottom. [HYPOTHESIS] marks an explanation we have not tested. [BLANK] and [UNVERIFIED] mark what is missing.

## What we see
We read NISAR L-band radar over a 20 x 20 km window near Novo Progresso, Pará, on 9 dates from 2026-06-26 to 2026-10-12 [R1]. Radar sees through cloud [S1][S2], so every pass gives a usable picture.

In these images, forest is bright in cross-polarised (HV) radar and cleared ground is darker. JAXA's forest-alert team describes the same contrast for its L-band system: "Forest: Bright, Non-Forest: Dark" [S3].

How well does one HV threshold separate the two? Against the Hansen forest map [S4], with the threshold chosen on the north half of the window and tested once on the south half [R2]:
- South half: 83.1 % of 100 m blocks correct (kappa 0.66). Calling every block "forest" would be 52.4 % correct [R3].
- Rondônia (a different area, 5 good dates), same threshold unchanged: 95.6 % correct (kappa 0.89), against 72.7 % for "all forest" [R3].

These measure agreement with a map made from optical imagery up to 2025, not with the ground. Clearing detections and their agreement with public alerts: [BLANK].

## Likely physical drivers
These are hypotheses. We did not measure them in our data.

**Why HV falls and HH rises when forest is cleared [HYPOTHESIS].**
- JAXA slides on a test site in Ucayali, Peru report two stages with PALSAR-2 L-band radar: early on, HH rose by 1.2 dB on average; later, HV fell by 3.2 dB [S5].
- Their explanation: HH rises because of branches left on the ground; HV falls because fallen trees remove the volume scattering of the standing canopy [S5].
- This was a different satellite and a different place. Whether it holds in Pará with NISAR is untested here, and HH can move either way [BLANK: cite a source if we keep this sentence].

**Slash and fire in the dry season [HYPOTHESIS].**
- A University of Wisconsin policy brief says fires "may be the final step of the deforestation process", set after trees are felled and left to dry [S6].
- Brazil's 2020 burning moratorium ran from 16 July to 13 November, which the brief calls the most critical months [S6]. Our dates (June to October) fall in a similar season. Whether 2026 fires affected our window: [UNVERIFIED]. We did not check fire data.
- Burned or debris-covered ground changes radar backscatter in ways we have not separated from clearing (our own known limit, CLAUDE.md) [R4].

**Cattle pasture [HYPOTHESIS for our window].**
- The Amazon Footprint Report 2025 finds cattle-linked deforestation "the main direct driver, resulting from pasture expansion", 78 % (6.7 million ha) of commodity-attributed deforestation in the Amazon region in 2018-2022 [S7]. That figure is for commodity-linked clearing region-wide, not for our window or for all clearing.
- Novo Progresso is a frontier town in northwest Pará [S8]; Mongabay reports trees there being cut to turn federal land into cattle pasture [S8].
- Most 2026 alerts in our window were re-clearing of land already cleared [BLANK: figure and file]. That points to pasture upkeep rather than new forest loss, but we have not shown it.

## What we do not see and why
- **Clearing the radar answers late.** HV tends to drop at a later stage of clearing [S5], so a detection can come after the alert. [BLANK: measured lag, from the lag table.]
- **Re-clearing of old clearings** is mostly outside our forest mask (forest = no Hansen loss 2001-2025 [S4], so previously cleared land is non-forest), so a forest-only method does not count it. [BLANK: share of alerts.]
- **Clearing before our first image, or after our last.** The forest map ends in 2025 [S4]; clearing between January and June 2026 is in neither map.
- **Selective logging**, rain and soil-moisture changes, flooded forest and fire effects: not handled (our known limits) [R4].
- **Small patches.** Our minimum patch size is [BLANK] ha; smaller clearings cannot be detected.
- **Anything outside two windows.** One 20 x 20 km area in Pará and one in Rondônia.

## Limitations
- The NISAR product is provisional: its catalogue entry says the data are "partially validated, and improvements are continuing" [S9].
- A bad granule (2026-07-12, Rondônia) and a geolocation problem in three early Rondônia dates are in the provisional product; the cause is unknown [R5]. We excluded those dates.
- Public alerts are a reference, not ground truth. Agreement is not accuracy.
- The forest/non-forest score uses the Hansen map as truth, and that map has its own errors that we did not measure [S4].
- Short record (9 dates in about 3.5 months); one area per location.
- We do not claim this stops deforestation, saves any carbon, or works everywhere.

## Future uses of NISAR
- NISAR scans nearly all land and ice twice every 12 days [S10], so a time series like ours could be built almost anywhere on land. Open data: the provisional GCOV collection is "openly shared, without restriction" [S9].
- NASA says NISAR "will also provide forest volume and biomass over time" [S11]. We did not test that.
- Because the radar works in cloud [S1][S2], it could add observations in the cloudiest forests to optical alert systems. Whether it improves alert timeliness is exactly what our remaining blank results would show: [BLANK].
- Once validated (not provisional) products exist: [UNVERIFIED, no source opened on release dates].

## Citations
Our own results (repo files, not external sources):
- [R1] `CLAUDE.md`, "CURRENT AOI" (window, track/frame, dates).
- [R2] `validation/PREREG_fnf.md`, committed before the run.
- [R3] `validation/fnf_metrics.json`, `data/REPORT.md` section 14 (`data/REPORT_section14.md`).
- [R4] `CLAUDE.md`, "Known limits".
- [R5] `CLAUDE.md`, "Rondonia (DEAD)", "Bad granules".

External sources (each opened in this session; page text read unless noted):
- [S1] eoPortal, "NISAR", last updated 2026-06-25: "Both frequencies penetrate clouds and forest canopies" (L-band wavelength 24 cm; launch 30 Jul 2025). https://www.eoportal.org/satellite-missions/nisar (the page text was read only in part; the quoted lines were verbatim)
- [S2] Hayashi & Nagatani (JAXA), "Introduction of the Forest Governance Initiative and JJ-FAST": "SAR acquires cloud-free image!" https://www.jica.go.jp/information/seminar/2019/ku57pq00002ll7hq-att/JJ-FAST_Introduction.pdf
- [S3] Same document as S2: "Forest: Bright / Non-Forest: Dark".
- [S4] Hansen et al. 2013, Science 342:850-853, as cited on the Earth Engine catalogue page (treecover2000 "canopy closure for all vegetation taller than 5m"; lossyear "Year of gross forest cover loss event"); the page shown is v1.12 (2000-2024) and marked superseded by v1.13, which we use. https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12
- [S5] Watanabe (Tokyo Denki Univ.), "JJ-FAST: JAXA-JICA Near-Real Time Deforestation Warning", Kyoto & Carbon Initiative, Jan 2017 (slides; test site Ucayali, Peru; PALSAR-2). https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2017_kc23/pdf/2-07b_KC23_JJ-FAST_Watanabe.pdf
- [S6] Schelly, Rausch & Gibbs, "Brazil's Cattle Sector Played Large Role in Fires During 2020 Moratorium", Frontiers in Forests and Global Change, 25 Nov 2021. https://www.frontiersin.org/journals/forests-and-global-change/articles/10.3389/ffgc.2021.760853/full
- [S7] "Technical brief: Drivers of Amazon deforestation in agricultural supply chains", Amazon Footprint Report 2025 (PDF hosted by WWF Germany). https://www.wwf.de/fileadmin/user_upload/Technical_brief_%E2%80%93_Amazon_Deforestation__1__compressed__1___1_.pdf
- [S8] Branford & Torres, "Amazon land speculators poised to gain control of vast public lands", Mongabay, 27 Mar 2017. https://news.mongabay.com/2017/03/amazon-land-speculators-poised-to-gain-control-of-vast-public-lands/
- [S9] "NISAR Provisional Geocoded Polarimetric Covariance Product (Version 1)", NASA Earthdata, site last updated 2026-11-06. https://www.earthdata.nasa.gov/data/catalog/asf-nisar-l2-gcov-provisional-v1-1
- [S10] "Mission Overview", NASA JPL NISAR press kit (undated, pre-launch wording): "twice every 12 days". https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/
- [S11] "NISAR: Monitoring Forest Disturbance", NASA/JPL fact sheet (2 pp., PDF). https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Timber_and_Forest_Disturbance.pdf

Searched but not cited, because the page could not be read: Riau PALSAR-2 paper (IOPscience, error page), RADD/GLAD alert product pages (the WUR page opened was a news article).
