"""Authenticated regional readers. No credentials persist; no incomplete day is published."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

import numpy as np
from environment_data import context, SMAP_NOTICE, save_new

def read_stream(fp,reader):
    import h5py
    raw=getattr(fp,'f',fp)
    with raw,h5py.File(raw,'r') as handle:return reader(handle)

def open_native_stream(access,url,reader):
    # Do not use earthaccess.open's background-prefetch cache with h5py.
    # Explicit block caching and request timeouts avoid waiting indefinitely
    # on a background future while the HDF5 library holds its internal lock.
    fs=access.get_fsspec_https_session()
    return read_stream(fs.open(url,'rb',block_size=262144,cache_type='blockcache',timeout=60),reader)

def screened(dataset, values):
    a=np.asarray(values,dtype=float)
    keep=np.isfinite(a)
    for k in ('_FillValue','missing_value','fmissing_value'):
        if k in dataset.attrs: keep &= a != float(np.asarray(dataset.attrs[k]).flat[0])
    for k,op in [('valid_min',np.greater_equal),('valid_max',np.less_equal)]:
        if k in dataset.attrs: keep &= op(a,float(np.asarray(dataset.attrs[k]).flat[0]))
    return a,keep

def soil_region(handle,bbox,window=None):
    if window is None:
        lat=handle['cell_lat'][:];lon=handle['cell_lon'][:]
        mask=(lon>=bbox[0])&(lon<=bbox[2])&(lat>=bbox[1])&(lat<=bbox[3])
        rr,cc=np.where(mask)
        if not len(rr): raise ValueError('No native cell centers inside region')
        window=(slice(rr.min(),rr.max()+1),slice(cc.min(),cc.max()+1),mask[rr.min():rr.max()+1,cc.min():cc.max()+1])
    rr,cc,mask=window;ds=handle['Geophysical_Data/sm_surface']
    if len(ds.shape)!=2 or ds.shape[0]<rr.stop or ds.shape[1]<cc.stop:
        raise ValueError('Native grid is incompatible with the cached regional window')
    units=str(ds.attrs.get('units',''))
    if 'm3 m-3' not in units: raise ValueError('Unexpected SMAP native units')
    a,valid=screened(ds,ds[rr,cc]);valid &= (a>=0)&(a<=0.9)
    # The native model stores residual snow fractions around 1e-8 in this tropical
    # sample. Treat <=1e-6 as numerical zero, rather than rejecting every cell.
    for name,test in [('soil_temp_layer1',lambda a:a>273.15),('land_fraction_snow_covered',lambda a:(a>=0)&(a<=1e-6))]:
        q=handle['Geophysical_Data/'+name];v,ok=screened(q,q[rr,cc]);valid &= ok&test(v)
    count=int(mask.sum());accepted=int((valid&mask).sum())
    if accepted!=count:raise ValueError('Incomplete valid regional coverage after moisture/frozen/snow screening')
    return {'value':float(a[mask].mean()),'native_cells':count},window

def daily_soil(samples):
    byday={}
    for s in samples:
        stamp=s['timestamp'];d=stamp[:10];clock=stamp[11:16]
        if clock not in {'01:30','04:30','07:30','10:30','13:30','16:30','19:30','22:30'}:raise ValueError('Unexpected three-hour interval center')
        if clock in byday.setdefault(d,{}):raise ValueError('Duplicate SMAP interval')
        byday[d][clock]=s
    return [{'date':d,'value':sum(s['value'] for s in slots.values())/8,'quality':'accepted','interval_count':8,'native_cells':min(s['native_cells'] for s in slots.values())}
            for d,slots in sorted(byday.items()) if len(slots)==8 and not SMAP_NOTICE['start']<=d<=SMAP_NOTICE['end']]

def rain_region(handle,bbox):
    datasets={}
    handle.visititems(lambda name,obj:datasets.update({name:obj}) if hasattr(obj,'shape') else None)
    def one(names):
        found=[v for k,v in datasets.items() if k.split('/')[-1] in names]
        if len(found)!=1:raise ValueError('Ambiguous or missing native field: '+str(names))
        return found[0]
    lat=one(('lat',))[:].ravel();lon=one(('lon',))[:].ravel()
    ri=np.where((lat>=bbox[1])&(lat<=bbox[3]))[0];ci=np.where((lon>=bbox[0])&(lon<=bbox[2]))[0]
    if not len(ri) or not len(ci):raise ValueError('No precipitation cells inside region')
    ds=one(('precipitation','precipitationCal'))
    units=str(ds.attrs.get('units','')).lower().replace(' ','')
    if not any(x in units for x in ('mm/day','mmd-1','mmday-1')):raise ValueError('Daily precipitation unit needs review: '+units)
    selection=[];axis=[]
    for size in ds.shape:
        if size==len(lat):selection.append(slice(ri.min(),ri.max()+1));axis.append('lat')
        elif size==len(lon):selection.append(slice(ci.min(),ci.max()+1));axis.append('lon')
        elif size==1:selection.append(0)
        else:raise ValueError('Unknown native dimension')
    a,valid=screened(ds,ds[tuple(selection)])
    a=a*float(ds.attrs.get('scale_factor',1))+float(ds.attrs.get('add_offset',0));valid &= np.isfinite(a)&(a>=0)
    if not valid.all():raise ValueError('Incomplete precipitation coverage after fill/range screening')
    if axis==['lon','lat']:a=a.T
    elif axis!=['lat','lon']:raise ValueError('Unknown coordinate order')
    weights=np.broadcast_to(np.cos(np.deg2rad(lat[ri]))[:,None],a.shape)
    return {'value':float(np.average(a,weights=weights)),'native_cells':int(a.size),'native_field':ds.name,'unit':units}

def main(output_root, authenticate=True):
    import earthaccess
    import h5py
    logging.disable(logging.CRITICAL)
    out=Path(output_root)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out.mkdir(parents=True,exist_ok=False)
    ctx=context();report={'products':{},'run_directory':str(out)}
    auth=earthaccess.login(strategy='interactive',persist=False) if authenticate else earthaccess.__auth__
    if not auth.authenticated:raise RuntimeError('Earthdata login not accepted')
    session=earthaccess.get_requests_https_session()
    def safe_error(exc):
        response=getattr(exc,'response',None)
        import traceback
        frames=traceback.extract_tb(exc.__traceback__)
        return {'error_type':type(exc).__name__,'http_status':getattr(response,'status_code',None),'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in frames[-4:]]}
    def stream(granule,reader,provider):
        # Open a single science link, excluding QA/XML sidecars.
        links=[u for u in granule.data_links() if re.search(r'\.(h5|nc4)(?:\?|$)',u)]
        if len(links)!=1:raise ValueError('Expected one native science link')
        return open_native_stream(earthaccess,links[0],reader)
    window=None;samples=[];sources=[];errors=[];interrupted=False
    # Reuse the already downloaded geolocation grid, avoiding a global lat/lon
    # read on every remote file. The native grid is checked on each region read.
    cached=Path(output_root).parent/'nasa-access'
    local=next(cached.rglob('SMAP_L4_SM_gph_20260812T223000_Vv8013_001.h5'),None)
    if local:
        with h5py.File(local,'r') as handle:_,window=soil_region(handle,ctx['bbox_wsen'])
    # Full UTC daily means on the six unaffected radar acquisition dates.
    for d in [d for d in ctx['nisar_dates'] if d>SMAP_NOTICE['end']]:
        found=earthaccess.search_data(short_name='SPL4SMGP',version='008',temporal=(d,d),bounding_box=tuple(ctx['bbox_wsen']))
        for g in found:
            title=g['umm']['GranuleUR'];match=re.search(r'_(\d{8})T(\d{6})_',title)
            if not match or match[1]!=d.replace('-',''):continue
            stamp=datetime.strptime(match[1]+match[2],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).isoformat()
            try:
                item,window=stream(g,lambda h:soil_region(h,ctx['bbox_wsen'],window),'NSIDC_CPRD')
                samples.append(dict(item,timestamp=stamp));sources.append(title)
            except KeyboardInterrupt:
                interrupted=True;break
            except Exception as exc:errors.append(dict(date=d,**safe_error(exc)))
            # This is a private run checkpoint, never a publishable daily series.
            checkpoint=out/'progress.json'
            checkpoint.write_text(json.dumps({'stage':'smap','date':d,'accepted_intervals':len(samples),'error_count':len(errors)}),encoding='utf-8')
            # Preserve actual accepted interval values after every request. A
            # partial download cannot be promoted to a complete daily mean.
            partial=out/'interval-checkpoint.json'
            temporary=out/'interval-checkpoint.tmp'
            temporary.write_text(json.dumps({'samples':samples,'granules':sources,'errors':errors},allow_nan=False),encoding='utf-8')
            temporary.replace(partial)
        print('SMAP day checked:',d,flush=True)
        if interrupted:break
    soil=daily_soil(samples)
    save_new(out/'smap.json',{'schema_version':1,**ctx,'kind':'smap','status':'available' if soil else 'unavailable','observations':soil,'quality_notice':SMAP_NOTICE,'samples':samples,'provenance':{'source_url':'https://nsidc.org/data/spl4smgp/versions/8','product':'SPL4SMGP','version':'008','unit':'m3/m3','native_crs':'EPSG:6933','spatial_resolution':'9 km EASE-Grid','quality_screening':'Native fill/range checks, snow fraction <=1e-6 (numerical-zero tolerance), soil temperature >273.15 K; every regional cell and all eight three-hour intervals required. Known geolocation-issue dates excluded. Dense-forest/model accuracy is not independently verified.','spatial_aggregation':'Equal-weight mean of equal-area native cell centers inside documented bbox, then mean of eight complete UTC three-hour intervals. Only radar acquisition dates processed.','retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'granules':sources,'geolocation_reprocessing_verified':False}})
    report['products']['smap']={'accepted_days':len(soil),'accepted_intervals':len(samples),'interrupted':interrupted,'errors':errors}
    rainfall=[];errors=[];sources=[];start=date.fromisoformat(ctx['start']);end=date.fromisoformat(ctx['end'])
    while start<=end and not interrupted:
        d=start.isoformat()
        try:
            found=earthaccess.search_data(short_name='GPM_3IMERGDL',version='07',temporal=(d,d),count=1)
            if not found:raise ValueError('No matching IMERG granule')
            g=found[0]
            try:item=stream(g,lambda h:rain_region(h,ctx['bbox_wsen']),'GES_DISC')
            except Exception:
                # Official authenticated HTTPS is a fallback to range streaming.
                link=next(u for u in g.data_links() if u.endswith('.nc4'))
                r=session.get(link,timeout=90);r.raise_for_status()
                import io
                with h5py.File(io.BytesIO(r.content),'r') as h:item=rain_region(h,ctx['bbox_wsen'])
            rainfall.append(dict(date=d,quality='accepted',**item));sources.append(g['umm']['GranuleUR'])
        except Exception as exc:
            errors.append(dict(date=d,**safe_error(exc)))
            # Repeated auth/schema failures must not cause 123 identical requests.
            if len(errors)>=3 and not rainfall:break
        print('IMERG day checked:',d,flush=True);start+=timedelta(days=1)
    save_new(out/'imerg.json',{'schema_version':1,**ctx,'kind':'imerg','status':'available' if rainfall else 'unavailable','observations':rainfall,'provenance':{'source_url':'https://gpm.nasa.gov/data/directory','product':'GPM_3IMERGDL','version':'07','unit':'mm/day','native_crs':'EPSG:4326','spatial_resolution':'0.1 degree','quality_screening':'Native fill/range checks and finite nonnegative daily precipitation; all regional cell centers required. Missing days retained as gaps.','spatial_aggregation':'Cos(latitude)-weighted regional mean at native cell centers inside bbox.','retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'granules':sources}})
    report['products']['imerg']={'accepted_days':len(rainfall),'errors':errors}
    save_new(out/'status.json',report);print('Finished. Report:',out/'status.json',flush=True)

if __name__=='__main__':main(sys.argv[1])
