/* Pure, testable evidence rules. No detection, probability, or validation model is fitted. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.EvidenceCore = api;
})(typeof window === 'undefined' ? globalThis : window, function () {
  'use strict';
  const DAY = 86400000;
  function dateOK(d) { return typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d) && Number.isFinite(Date.parse(d)) && new Date(Date.parse(d)).toISOString().slice(0,10) === d; }
  function covered(lon,lat,b) { return Array.isArray(b) && b.length === 4 && b.every(Number.isFinite) && Number.isFinite(lon) && Number.isFinite(lat) && b[0] <= lon && lon <= b[2] && b[1] <= lat && lat <= b[3]; }
  function validSeries(data, kind) {
    if (data?.schema_version !== 1 || data.kind !== kind || data.status !== 'available' || !Array.isArray(data.observations) || !data.observations.length || !data.provenance || data.provenance.unit !== (kind === 'imerg' ? 'mm/day' : 'm3/m3') || !Array.isArray(data.bbox_wsen) || data.bbox_wsen.length!==4 || !data.bbox_wsen.every(Number.isFinite)) return null;
    const seen = new Set();
    for (const r of data.observations) {
      if (!dateOK(r.date) || seen.has(r.date) || r.quality !== 'accepted' || !Number.isFinite(r.value) || r.value < 0 || (kind === 'smap' && r.value > 1)) return null;
      seen.add(r.date);
    }
    return data;
  }
  function rain(rows, acquisition, n) {
    if (!dateOK(acquisition) || ![3,7,14].includes(n)) return {value:null,complete_days:0,expected_days:n};
    const entries = new Map(rows.map(r => [r.date,r.value]));
    let complete = 0, value = 0;
    for (let i=1;i<=n;i++) {
      const d = new Date(Date.parse(acquisition)-i*DAY).toISOString().slice(0,10), v = entries.get(d);
      if (Number.isFinite(v) && v >= 0) { complete++; value+=v; }
    }
    return {value:complete===n ? value : null, complete_days:complete,expected_days:n};
  }
  function smapAt(data,d) {
    if (!data || !dateOK(d)) return null;
    const rows = data.observations.filter(r => data.provenance.geolocation_reprocessing_verified === true || r.date < '2026-05-14' || r.date > '2026-07-28');
    const row = [...rows].sort((a,b)=>Math.abs(Date.parse(a.date)-Date.parse(d))-Math.abs(Date.parse(b.date)-Date.parse(d)) || a.date.localeCompare(b.date))[0];
    return row && Math.abs(Date.parse(row.date)-Date.parse(d))<=3*DAY ? row : null;
  }
  function distanceKm(a,b) {
    const rad = x=>x*Math.PI/180, dlat=rad(b[1]-a[1]),dlon=rad(b[0]-a[0]);
    const h=Math.sin(dlat/2)**2+Math.cos(rad(a[1]))*Math.cos(rad(b[1]))*Math.sin(dlon/2)**2;
    return 6371.0088*2*Math.asin(Math.min(1,Math.sqrt(h)));
  }
  function validFire(fc) {
    return fc?.schema_version===1 && fc.type==='FeatureCollection' && fc.status==='available' && fc.coverage_complete===true && dateOK(fc.start) && dateOK(fc.end) && Array.isArray(fc.features) && fc.features.every(f=>f?.geometry?.type==='Point' && Array.isArray(f.geometry.coordinates) && f.geometry.coordinates.length===2 && covered(...f.geometry.coordinates,fc.bbox_wsen) && dateOK(f.properties?.date) && typeof f.properties?.confidence === 'string') ? fc : null;
  }
  function firesNear(fc,point,d) {
    if (!fc || !dateOK(d) || !covered(...point,fc.bbox_wsen)) return null;
    const low=Date.parse(d)-7*DAY,high=Date.parse(d)+7*DAY;
    // A complete +/-7 day query is required to interpret zero matches.
    if (Date.parse(fc.start)>low || Date.parse(fc.end)<high) return null;
    return fc.features.map(f=>({feature:f,distance_km:distanceKm(point,f.geometry.coordinates)})).filter(o=>o.distance_km<=5 && Date.parse(o.feature.properties.date)>=low && Date.parse(o.feature.properties.date)<=high).sort((a,b)=>a.distance_km-b.distance_km);
  }
  function interpretation(kind,p) {
    if (kind !== 'det' && p.category==='alert_supported') return {category:'Radar flag with independent alert-product agreement',rule:'The shipped patch category reports at least one constituent block with a GLAD-L or GLAD-S2 alert in the pre-registered 2026-06-26 to 2026-11-05 window. That means the products agree. It isn\'t confirmation from the field.'};
    return {category:'Insufficient evidence for confirmation',rule:'A radar flag by itself doesn\'t confirm clearing, and neither does a clear optical image or environmental data nearby. We have no calibrated probability and no automatic optical label.'};
  }
  function opticalPair(meta,lon,lat,d) {
    if (!meta || !covered(lon,lat,meta.bounds_lonlat) || !dateOK(d)) return {before:null,after:null};
    const rows=(Array.isArray(meta.passes)?meta.passes:[]).filter(r=>dateOK(r.date) && typeof r.file==='string' && /^[\w.-]+\.webp$/.test(r.file) && Number.isFinite(r.clear_fraction) && r.clear_fraction>=0 && r.clear_fraction<=1).sort((a,b)=>a.date.localeCompare(b.date));
    const before=rows.filter(r=>r.date<d && Date.parse(d)-Date.parse(r.date)<=30*DAY).at(-1)||null;
    const after=rows.find(r=>r.date>=d && Date.parse(r.date)-Date.parse(d)<=30*DAY)||null;
    return {before,after};
  }
  function validOptical(meta) {
    const g=meta?.grid,b=g?.bounds;
    return g?.crs==='EPSG:3857' && Number.isInteger(g.width) && g.width>0 && Number.isInteger(g.height) && g.height>0 && Array.isArray(b) && b.length===4 && b.every(Number.isFinite) && b[2]>b[0] && b[3]>b[1] && Array.isArray(meta.bounds_lonlat) && Array.isArray(meta.passes) ? meta : null;
  }
  return {DAY,dateOK,covered,validSeries,rain,smapAt,distanceKm,validFire,firesNear,interpretation,opticalPair,validOptical};
});
