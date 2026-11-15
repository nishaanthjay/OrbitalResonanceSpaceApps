/* Environmental context and investigation UI. Every observation must pass evidence-core validation. */
'use strict';
(() => {
  const E=EvidenceCore, id=s=>document.getElementById(s), node=(t,text,cls)=>{const n=document.createElement(t);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fetchJSON=async p=>{try{const r=await fetch(p);return r.ok?await r.json():null;}catch{return null;}};
  let firePromise=null;
  function ensureFire(){ // firms.geojson (1.2 MB) is fetched only when the section is near the viewport or an investigation opens
    if(firePromise)return firePromise;
    firePromise=(async()=>{const f=data.access?.datasets?.firms?.file==='firms.geojson'?await fetchJSON('data/environment/firms.geojson'):null;data.fire=E.validFire(f);data.fireTried=true;renderEnvironment();})();
    return firePromise;
  }
  const configuredRegistry=document.body?.dataset?.environmentRegistry;
  const registry=/^data\/environment\/[\w.-]+\.json$/.test(configuredRegistry||'')?configuredRegistry:'data/environment/access.json';
  const data={access:null,imerg:null,smap:null,fire:null,optical:null,big:null}, dates=[];
  let selected=null, opticalVersion=0, lastFocus=null, ready=false;
  const dialog=id('investigation'), nf=v=>Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:2}):'Not available';
  function facts(box,rows){const dl=node('dl');rows.forEach(([k,v])=>dl.append(node('dt',k),node('dd',v)));box.append(dl);}
  function timeline(container,series,unit){
    container.replaceChildren();if(!series?.length)return;
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 360 160');svg.setAttribute('role','img');svg.setAttribute('aria-label',`Regional observations, ${unit}`);
    const low=Date.parse(series[0].date),high=Date.parse(series.at(-1).date),max=Math.max(...series.map(r=>r.value),0.01),X=d=>35+(Date.parse(d)-low)/Math.max(high-low,E.DAY)*310,Y=v=>120-v/max*95;
    for(const r of series){const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',X(r.date));circle.setAttribute('cy',Y(r.value));circle.setAttribute('r','3');circle.setAttribute('fill','#8fa58b');const title=document.createElementNS(ns,'title');title.textContent=`${r.date}: ${r.value} ${unit}`;circle.append(title);svg.append(circle);}
    for(const [x,y,text] of [[0,20,`${nf(max)} ${unit}`],[35,148,series[0].date],[245,148,series.at(-1).date]]){const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.textContent=text;svg.append(t);}
    const d=id('env-date').value;if(E.dateOK(d)&&Date.parse(d)>=low&&Date.parse(d)<=high){const line=document.createElementNS(ns,'line');for(const [k,v]of Object.entries({x1:X(d),x2:X(d),y1:10,y2:125,stroke:'#e5e9df','stroke-dasharray':'3 3'}))line.setAttribute(k,v);svg.append(line);}
    container.append(svg);const details=node('details'),summary=node('summary','View observation table'),table=node('table');const head=node('tr');head.append(node('th','Date (UTC)'),node('th',unit));table.append(head);series.forEach(r=>{const tr=node('tr');tr.append(node('td',r.date),node('td',nf(r.value)));table.append(tr);});details.append(summary,table);container.append(details);
  }
  function sourceState(kind){const good=data[kind];id(`env-${kind}-state`).textContent=good?'Available, quality-screened regional observations':data.access?.datasets?.[kind]?.status_label||'Not available';id(`env-${kind}-reason`).textContent=good?`${good.observations.length} accepted regional daily observations. ${good.provenance.spatial_resolution}. ${good.provenance.spatial_aggregation}.`:data.access?.datasets?.[kind]?.reason||'No validated regional dataset is installed.';}
  function renderEnvironment(){
    const date=id('env-date').value;for(const key of ['imerg','smap'])sourceState(key);
    timeline(id('env-imerg-chart'),data.imerg?.observations,'mm/day');timeline(id('env-smap-chart'),data.smap?.observations.filter(r=>data.smap.provenance.geolocation_reprocessing_verified===true||r.date<'2026-05-14'||r.date>'2026-07-28'),'m³/m³');
    const rain=id('env-rain-detail');rain.replaceChildren();if(data.imerg){facts(rain,[3,7,14].map(n=>{const r=E.rain(data.imerg.observations,date,n);return [`Previous ${n} complete UTC days`,r.value===null?`Not available (${r.complete_days}/${n} days present)`:`${nf(r.value)} mm`];}));}
    const sm=data.smap&&E.smapAt(data.smap,date);id('env-soil-detail').textContent=sm?`${nf(sm.value)} m³/m³ on ${sm.date}, nearest daily regional value within ±3 days. A 9 km modeled product, not local patch moisture.`:'No accepted soil-moisture observation matched within ±3 days. Dates affected by the May–July geolocation issue are withheld unless reprocessing is documented.';
    id('env-fire-state').textContent=data.fire?'Available, complete downloaded date coverage':!data.fireTried?'Checking dataset':data.access?.datasets?.firms?.status_label||'Not available';id('env-fire-reason').textContent=data.fire?`${data.fire.features.length.toLocaleString('en-US')} VIIRS detections in the downloaded region and period. ${data.fire.provenance?.processing_note||''} Confidence is the provider code, not a clearing probability.`:!data.fireTried?'':data.access?.datasets?.firms?.reason||'No validated historical FIRMS observations are installed.';
    id('env-fire-toggle').disabled=!data.fire;updateFireMap();if(selected)renderInvestigation(false);
  }
  function updateFireMap(){
    if(typeof map==='undefined'||!map.isStyleLoaded()||!data.fire)return;
    if(!map.getSource('environment-fire')){map.addSource('environment-fire',{type:'geojson',data:data.fire});map.addLayer({id:'environment-fire',type:'circle',source:'environment-fire',paint:{'circle-radius':5,'circle-color':'#b68b52','circle-stroke-width':1,'circle-stroke-color':'#e5e9df'}});map.on('click','environment-fire',e=>{const p=e.features?.[0]?.properties;if(!p)return;const text=`VIIRS thermal anomaly • ${p.acquired_at_utc} • confidence ${p.confidence} • FRP ${p.frp_mw??'not available'} MW. Not burned area or proof of fire-caused clearing.`;new maplibregl.Popup().setLngLat(e.lngLat).setText(text).addTo(map);});}
    const d=id('env-date').value,lo=new Date(Date.parse(d)-7*E.DAY).toISOString().slice(0,10),hi=new Date(Date.parse(d)+7*E.DAY).toISOString().slice(0,10);
    map.setFilter('environment-fire',['all',['>=',['get','date'],lo],['<=',['get','date'],hi]]);map.setLayoutProperty('environment-fire','visibility',id('env-fire-toggle').checked?'visible':'none');
  }
  const toMerc=(lon,lat)=>[6378137*lon*Math.PI/180,6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))];
  function opticalFigure(row,title,point,feature,token){
    const figure=node('figure'),canvas=node('canvas');canvas.width=240;canvas.height=240;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',`${title} Sentinel-2 crop at selected patch`);figure.append(canvas);
    if(!row){figure.append(node('figcaption',`${title}: no dated scene within 30 days on the appropriate side of the first-change date.`));return figure;}
    figure.append(node('figcaption',`${title}: ${row.date}. 60 km box clear fraction ${(100*row.clear_fraction).toFixed(1)}%; local cloud fraction is not measured. Acquisition ${row.scene_id}.`));
    const image=new Image();image.onload=()=>{
      if(token!==opticalVersion)return;const ctx=canvas.getContext('2d'),grid=data.optical.grid,b=grid.bounds,[x,y]=toMerc(...point),scale=(b[2]-b[0])/image.naturalWidth,crop=3200/scale,px=(x-b[0])/scale,py=(b[3]-y)/((b[3]-b[1])/image.naturalHeight),sx=px-crop/2,sy=py-crop/2;
      ctx.fillStyle='#193426';ctx.fillRect(0,0,240,240);ctx.drawImage(image,sx,sy,crop,crop,0,0,240,240);ctx.strokeStyle='#e5e9df';ctx.lineWidth=1.2;
      const polygons=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.type==='MultiPolygon'?feature.geometry.coordinates:[];
      for(const poly of polygons)for(const ring of poly){ctx.beginPath();ring.forEach(([lon,lat],i)=>{const [mx,my]=toMerc(lon,lat),cx=((mx-b[0])/scale-sx)/crop*240,cy=((b[3]-my)/((b[3]-b[1])/image.naturalHeight)-sy)/crop*240;i?ctx.lineTo(cx,cy):ctx.moveTo(cx,cy);});ctx.closePath();ctx.stroke();}
    };image.onerror=()=>{if(token===opticalVersion)figure.append(node('p','Optical image failed to load. Acquisition metadata alone cannot support a visual interpretation.','invest-status'));};image.src='data/explore/optical/'+row.file;return figure;
  }
  function renderInvestigation(images=true){
    if(!selected)return;const {feature:f,kind,point,dates:ds}=selected,p=f.properties,first=p.first_switch_date||p.first_date||p.first_flagged,d=id('env-date').value||first;
    id('invest-title').textContent=`${kind==='det'?'Detection':'Flagged patch'} ${p.id}`;const interpretation=E.interpretation(kind,p);id('invest-category').textContent=interpretation.category;id('invest-rule').textContent=interpretation.rule;
    const radar=id('invest-radar');radar.replaceChildren();facts(radar,[['First flagged / first class switch',first||'Not available'],['Mapped patch area',`${nf(p.area_ha)} ha`],['Acquisition count',String(ds.length)],['Radar scope',kind==='det'?'Original 1 dB detector; retained for the record.':'Fixed class-switch rule on 100 m blocks.'],['Evidence confidence','Not calibrated; no probability is calculated.']]);
    const details=node('details'),summary=node('summary','HH/HV values and changes from the first available acquisition'),table=node('table'),head=node('tr');['NISAR date','HH dB','HV dB','ΔHV dB'].forEach(t=>head.append(node('th',t)));table.append(head);const hv=p.hv_series_db,hh=p.hh_series_db;ds.forEach((date,i)=>{const tr=node('tr'),v=hv?.[i],base=hv?.[0];[date,nf(hh?.[i]),nf(v),nf(Number.isFinite(v)&&Number.isFinite(base)?v-base:null)].forEach(v=>tr.append(node('td',String(v))));table.append(tr);});details.append(summary,table);radar.append(details);
    if(images){const box=id('invest-optical');box.replaceChildren();const token=++opticalVersion,pair=E.opticalPair(data.optical,...point,first);box.append(opticalFigure(pair.before,'Before',point,f,token),opticalFigure(pair.after,'After',point,f,token));id('invest-optical-note').textContent='Nearest available scene strictly before / on-or-after the first-change date, within 30 days. Crop: 3.2 km square on the exported EPSG:3857 grid; imagery is resampled to about 100 m. White outline: radar patch. No cloud masking or patch-level visual label exists. Optical support: unassessed; an independent reviewer must examine the dates and local clouds.';}
    const env=id('invest-environment');env.replaceChildren();env.append(node('p',`Context date: ${d}. Environmental correlations do not establish causes.`));
    if(data.imerg&&E.covered(...point,data.imerg.bbox_wsen)){facts(env,[3,7,14].map(n=>{const r=E.rain(data.imerg.observations,d,n);return [`Rainfall, previous ${n} UTC days`,r.value===null?'Not available: incomplete window':`${nf(r.value)} mm (regional)`];}));}
    if(data.smap){const sm=E.covered(...point,data.smap.bbox_wsen)&&E.smapAt(data.smap,d);env.append(node('p',sm?`Regional SMAP: ${nf(sm.value)} m³/m³ on ${sm.date}. Not a patch measurement.`:'SMAP: no accepted regional match.'));}
    const near=E.firesNear(data.fire,point,d);env.append(node('p',near===null?'FIRMS proximity: unavailable or incomplete ±7-day coverage.':`${near.length} thermal anomalies within 5 km of the patch centroid and ±7 days (retrospective search). Proximity does not imply causation.`));
    if(near?.length){const list=node('ul',undefined,'fire-meta');near.forEach(o=>{const q=o.feature.properties;list.append(node('li',`${q.acquired_at_utc} · ${nf(o.distance_km)} km from centroid · confidence ${q.confidence} · ${q.instrument||'VIIRS'} · FRP ${nf(q.frp_mw)} MW`));});env.append(list);}
    env.append(node('p','Wet/dry anomaly: not assessed. No long-term rainfall or soil-moisture climatology is installed. Moisture remains a possible confounder, not an assigned cause.'));
  }
  function select(event){
    const s=event.detail;if(!s?.feature?.properties)return;selected=s;if(ready)ensureFire();
    if(document.body?.classList?.contains('touring')&&!s.allowTour)return;
    const d=s.feature.properties.first_switch_date||s.feature.properties.first_date||s.feature.properties.first_flagged;if(dates.includes(d))id('env-date').value=d;renderEnvironment();renderInvestigation(true);lastFocus=document.activeElement;if(!dialog.open)dialog.show();id('invest-title').focus({preventScroll:true});
  }
  document.addEventListener('evidence:selection',select);
  document.addEventListener('evidence:tour',()=>{if(selected)select({detail:{...selected,allowTour:true}});});
  document.addEventListener('evidence:tour-end',()=>{if(dialog.open)dialog.close();});
  id('tour-btn').addEventListener('click',()=>{if(dialog.open)dialog.close();});
  document.addEventListener('evidence:map-date',event=>{if(dates.includes(event.detail?.date)){id('env-date').value=event.detail.date;renderEnvironment();}});
  document.addEventListener('explore:ready',()=>{updateFireMap();id('invest-example').disabled=!state.bigMeta?.watch_priorities?.items?.length;});
  id('invest-close').onclick=()=>{dialog.close();lastFocus?.focus?.({preventScroll:true});};dialog.addEventListener('cancel',event=>{event.preventDefault();id('invest-close').click();});
  addEventListener('keydown',event=>{if(event.key==='Escape'&&dialog.open)id('invest-close').click();});
  id('env-date').onchange=renderEnvironment;id('env-fire-toggle').onchange=updateFireMap;
  id('invest-example').onclick=async()=>{if(!ready||typeof state==='undefined'||!state.bigMeta)return;const item=state.bigMeta.watch_priorities?.items?.[0];if(!item)return;id('invest-example').disabled=true;try{document.getElementById('explore').scrollIntoView({behavior:'instant'});await openLost(item.id);}finally{id('invest-example').disabled=false;}};
  Promise.all([registry,'data/explore/optical/optical.json','data/explore/big/big.json'].map(fetchJSON)).then(async([access,optical,big])=>{
    const load=(key,file)=>access?.datasets?.[key]?.file===file?fetchJSON('data/environment/'+file):Promise.resolve(null);
    const [rain,soil]=await Promise.all([load('imerg','imerg.json'),load('smap','smap.json')]);
    data.access=access;data.imerg=E.validSeries(rain,'imerg');data.smap=E.validSeries(soil,'smap');data.optical=E.validOptical(optical);data.big=big;dates.push(...(big?.dates||[]));id('env-date').replaceChildren(...dates.map(d=>new Option(d,d)));id('env-date').disabled=!dates.length;if(dates.length)id('env-date').value=dates.at(-1);ready=true;renderEnvironment();if('IntersectionObserver' in window){new IntersectionObserver((e,o)=>{if(e.some(x=>x.isIntersecting)){ensureFire();o.disconnect();}},{rootMargin:'600px'}).observe(id('environment'));}else ensureFire();if(selected)renderInvestigation(true);if(typeof state!=='undefined')id('invest-example').disabled=!state.bigMeta?.watch_priorities?.items?.length;
  }).catch(()=>{id('env-load-status').textContent='Environmental evidence could not initialize. Radar and optical exploration remain available.';});
})();
