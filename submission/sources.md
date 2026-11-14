# Sources

Status: **opened** = page text read in this session (2026-11-14); **not opened** = listed from team files, not re-read here, treat as [UNVERIFIED] until checked. Access date for all web pages: 2026-11-14.

## Opened (used in story.md / README.md)
1. eoPortal, "NISAR (NASA-ISRO Synthetic Aperture Radar)", last updated 2026-06-25. Launch 2025-07-30; both bands penetrate clouds and forest canopy; L-band 24 cm. Page read only in part. https://www.eoportal.org/satellite-missions/nisar
2. NASA JPL, "Mission Overview" (NISAR press kit, undated, pre-launch wording). "Twice every 12 days". https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/
3. NASA/JPL, "NISAR: Monitoring Forest Disturbance" (2-page fact sheet). Forest volume and biomass over time. https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Timber_and_Forest_Disturbance.pdf
4. NASA Earthdata, "NISAR Provisional Geocoded Polarimetric Covariance Product (Version 1)", site updated 2026-11-06. Provisional, partially validated, openly shared. https://www.earthdata.nasa.gov/data/catalog/asf-nisar-l2-gcov-provisional-v1-1
5. ASF, "Geocoded Polarimetric Covariance (GCOV) - NISAR Data User Guide". Gamma-0 power, polarizations vary with acquisition mode. https://nisar-docs.asf.alaska.edu/gcov/
6. Hayashi & Nagatani (JAXA), "Introduction of the Forest Governance Initiative and JJ-FAST". SAR gives cloud-free images; forest bright, non-forest dark. https://www.jica.go.jp/information/seminar/2019/ku57pq00002ll7hq-att/JJ-FAST_Introduction.pdf
7. Watanabe (Tokyo Denki Univ.), "JJ-FAST: JAXA-JICA Near-Real Time Deforestation Warning", Kyoto & Carbon Initiative, Jan 2017. HH +1.2 dB early, HV -3.2 dB late (Ucayali, Peru, PALSAR-2). https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2017_kc23/pdf/2-07b_KC23_JJ-FAST_Watanabe.pdf
8. Schelly, Rausch & Gibbs, "Brazil's Cattle Sector Played Large Role in Fires During 2020 Moratorium", Frontiers in Forests and Global Change 4, 25 Nov 2021, doi 10.3389/ffgc.2021.760853. https://www.frontiersin.org/journals/forests-and-global-change/articles/10.3389/ffgc.2021.760853/full
9. "Technical brief: Drivers of Amazon deforestation in agricultural supply chains", Amazon Footprint Report 2025 (PDF on wwf.de; publisher and authors not confirmed from the text). 78 % (6.7 Mha) cattle, 2018-2022. https://www.wwf.de/fileadmin/user_upload/Technical_brief_%E2%80%93_Amazon_Deforestation__1__compressed__1___1_.pdf
10. Branford & Torres, "Amazon land speculators poised to gain control of vast public lands", Mongabay, 2017-03-27. Novo Progresso in northwest Pará. https://news.mongabay.com/2017/03/amazon-land-speculators-poised-to-gain-control-of-vast-public-lands/
11. Hansen et al. 2013, "High-Resolution Global Maps of 21st-Century Forest Cover Change", Science 342:850-853, doi 10.1126/science.1244693, as cited on the Earth Engine catalogue page (shows v1.12, marked superseded by v1.13, which we use; band definitions read there). https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12
12. Global Forest Watch data API, dataset `wur_radd_alerts` metadata (version v20261108; coverage dates only, no definitions). https://data-api.globalforestwatch.org/dataset/wur_radd_alerts/latest
13. Wageningen University & Research news item, "AI system predicts illegal deforestation..." (2025-09-10): RADD uses Sentinel-1 radar, which sees through clouds. Not a product page. https://www.wur.nl/en/research-results/chair-groups/environmental-sciences/laboratory-of-geo-information-science-and-remote-sensing/research/sensing-measuring/radd-forest-disturbance-alert.htm

## Our own data and code
- Repo: https://github.com/nishaanthjay/OrbitalResonanceSpaceApps. Results: `validation/fnf_metrics.json`, `validation/PREREG_fnf.md`, `CLAUDE.md`. Live map: https://sars-deforest.vercel.app
- S Para stack (sha256 0e8ab5dd37f8893017b146aa66380c0af06b38b3ee0fdc0e41420dd7ad4b267e): https://drive.google.com/file/d/1mPg7_Msq-7oKh3xMiqappdHFVl9K-RyC/view?usp=sharing
- Product used: NISAR L2 GCOV provisional (`NISAR_L2_GCOV_PROVISIONAL_V1`), via NASA Earthdata / ASF. NISAR spec D-102274 Rev D, cited in CLAUDE.md (not opened here).

## Not opened (from team files) [UNVERIFIED]
- Reference alerts, as described in `validation/README.md` (checked by the validation owner against the GFW API on 2026-11-14, not re-read here): GLAD-L (Hansen et al. 2016), GLAD-S2 (Pickens et al. 2020), RADD (Reiche et al. 2021), GFW integrated alerts; licence CC BY 4.0 as stated there. Full citations and access dates to be added from the original papers: [BLANK].
  - https://data.globalforestwatch.org/datasets/gfw::integrated-deforestation-alerts/about
  - https://glad-forest-alert.appspot.com/
  - https://glad.earthengine.app/view/s2-forest-alerts
  - https://browser.dataspace.copernicus.eu/ (Sentinel-2 viewer for hand labels)
- Earlier team list: https://nisar-docs.asf.alaska.edu/earthaccess/ , https://nisar-docs.asf.alaska.edu/asf-search/ , https://www.eorc.jaxa.jp/ALOS/en/kyoto/jan2018_kc24/pdf/3-01_KC24_Watanabe_TDU.pdf , https://www.eorc.jaxa.jp/ALOS/jp/activity/kyoto/pdf/3-01_KC25_Watanabe.pdf , https://www.eorc.jaxa.jp/ALOS/jp/activity/kyoto/pdf/1-07_PKC1_Watanabe.pdf
- Web map libraries and basemap, per `web/README.md`: MapLibre GL JS 5.9.0, `@geomatico/maplibre-cog-protocol` 0.10.0 (MIT), OpenFreeMap "liberty" style. Licences and required attribution text: [BLANK].
- ESA WorldCover and JAXA PALSAR-2 FNF were considered as forest masks and not used.

## Searched, could not read (not cited)
IOPscience Riau PALSAR-2 paper (doi 10.1088/1748-9326/10/3/034014, error page); JAXA KC Phase 2 reports; Science Panel for the Amazon 2021 chapter 19.
