"""Reproducible environmental access audit, FIRMS acquisition, and regional CSV import.

No credentials or response login pages are saved. Existing outputs are never overwritten.
IMERG/SMAP CSVs must be genuine, provider-quality-screened regional exports with provenance.
This script does not modify NISAR detection or validation.
"""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

WEB = Path(__file__).resolve().parents[1]
SOURCES = {
    'imerg': {'name': 'NASA GPM IMERG', 'collection': 'GPM_3IMERGDL', 'resolution': '0.1 degree grid', 'unit': 'mm/day', 'source': 'https://gpm.nasa.gov/data/directory', 'access': 'Earthdata Login and GES DISC data access, or a PPS registered account. Late Run is selected because Final Run can lag by months.'},
    'smap': {'name': 'NASA SMAP L4 SPL4SMGP v8', 'collection': 'SPL4SMGP', 'resolution': '9 km EASE-Grid; 3-hourly land-model assimilation', 'unit': 'm3/m3', 'source': 'https://nsidc.org/data/spl4smgp/versions/8', 'access': 'Earthdata Login; order a geographic subset through NSIDC / Harmony. Preserve provider quality and assimilation diagnostics.'},
    'firms': {'name': 'NASA FIRMS VIIRS S-NPP standard processing', 'resolution': 'nominal 375 m detection footprint; not a burned-area product', 'unit': 'thermal anomaly; FRP in MW', 'source': 'https://firms.modaps.eosdis.nasa.gov/api/area/', 'access': 'A free FIRMS MAP_KEY is needed. Set FIRMS_MAP_KEY in your local environment, never in a frontend file. Check data_availability before historical retrieval.'},
}
SMAP_NOTICE = {'source': SOURCES['smap']['source'], 'start': '2026-05-14', 'end': '2026-07-28', 'note': 'NSIDC reports a SMAP geolocation issue in this interval; L4 reprocessing is pending as of 2026-11-15. Require a documented reprocessed source before using these dates.'}

def save_new(path, value):
    payload = json.dumps(value, indent=2, allow_nan=False) + '\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(payload)

def read_url(url, limit=4_000_000):
    req = Request(url, headers={'User-Agent': 'OrbitalResonance-research/phase2'})
    with urlopen(req, timeout=25) as r:
        content = r.read(limit + 1)
        if len(content) > limit:
            raise ValueError('Response exceeds lightweight acquisition limit')
        return content, r.headers, r.url

def context():
    meta = json.loads((WEB / 'data/explore/big/big.json').read_text())
    dates = meta['dates']
    return {'bbox_wsen': meta['bounds_lonlat'], 'crs': 'EPSG:4326', 'nisar_dates': dates,
            'start': (date.fromisoformat(dates[0]) - timedelta(days=14)).isoformat(), 'end': dates[-1],
            'scope': 'Southern Para 60 km box only; not the full NISAR frame.'}

def probe(output):
    ctx = context()
    audit = {'schema_version': 1, 'checked_at_utc': datetime.now(timezone.utc).isoformat(), **ctx, 'datasets': {}, 'smap_notice': SMAP_NOTICE}
    for key in ['imerg', 'smap']:
        info = dict(SOURCES[key], status='unavailable', observations=[], probes=[])
        params = {'short_name': info['collection'], 'temporal': f"{ctx['start']}T00:00:00Z,{ctx['end']}T23:59:59Z", 'bounding_box': ','.join(map(str,ctx['bbox_wsen'])), 'page_size': 1}
        url = 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params)
        try:
            body, headers, _ = read_url(url)
            entries = json.loads(body)['feed']['entry']
            info['probes'].append({'url': url, 'status': 200, 'matching_granules': headers.get('CMR-Hits'), 'returned': len(entries)})
            if entries:
                granule = entries[0]
                info['example_granule'] = {k: granule.get(k) for k in ['id','title','time_start','time_end']}
                links = [l['href'] for l in granule.get('links',[]) if l.get('rel','').endswith('/data#') and not l.get('inherited') and l.get('href','').startswith('https://')]
                if links:
                    link = links[0]
                    host = urlsplit(link).hostname or ''
                    if host.endswith('.nasa.gov') or host.endswith('.nsidc.org') or host.endswith('.earthdatacloud.nasa.gov'):
                        try:
                            # A small read tests unauthenticated access, not a complete science download.
                            with urlopen(Request(link, headers={'Range':'bytes=0-1023'}),timeout=25) as response:
                                chunk = response.read(1024)
                                info['probes'].append({'url':link, 'status':response.status, 'content_type':response.headers.get('Content-Type'), 'login_redirect': 'urs.earthdata.nasa.gov' in response.url, 'bytes_probed':len(chunk)})
                        except HTTPError as exc:
                            info['probes'].append({'url':link, 'status':exc.code})
                        except (URLError,TimeoutError,OSError):
                            info['probes'].append({'url':link, 'status':'network_unavailable'})
                info['reason'] = 'Catalog metadata retrieved; no quality-screened regional measurements downloaded. Follow the documented authenticated subset workflow.'
            else:
                info['reason'] = 'No matching granules returned by this catalog query. This is not evidence of zero precipitation or soil moisture.'
        except HTTPError as exc:
            info['probes'].append({'url':url,'status':exc.code}); info['reason'] = 'Catalog access failed; measurements not available.'
        except (URLError,TimeoutError,OSError,ValueError,KeyError):
            info['probes'].append({'url':url,'status':'request_failed'}); info['reason'] = 'Catalog request could not be completed.'
        audit['datasets'][key] = info
    # Test the documented public PPS directory as an independent access route.
    url = 'https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/late/2026/06/'
    try:
        body,headers,final = read_url(url)
        audit['datasets']['imerg']['probes'].append({'url':url,'status':200,'content_type':headers.get('Content-Type'),'login_redirect':'registration' in final})
    except HTTPError as exc:
        audit['datasets']['imerg']['probes'].append({'url':url,'status':exc.code})
    except (URLError,TimeoutError,OSError,ValueError):
        audit['datasets']['imerg']['probes'].append({'url':url,'status':'request_failed'})
    audit['datasets']['firms'] = dict(SOURCES['firms'], status='unavailable', observations=[], reason='No FIRMS_MAP_KEY supplied; no historical fire measurements requested. Missing fire data is not evidence of no fires.')
    save_new(output,audit)
    print(json.dumps({k:{'status':v['status'],'probes':v.get('probes',[])} for k,v in audit['datasets'].items()},indent=2))

def aggregate_rain(rows, target):
    """Previous complete UTC days [target-N,target); a missing day invalidates that window."""
    index = {}
    for row in rows:
        d = date.fromisoformat(row['date']); value = float(row['value'])
        if d in index or not math.isfinite(value) or value < 0:
            raise ValueError('Duplicate, negative, or nonfinite daily precipitation')
        index[d] = value
    t = date.fromisoformat(target)
    return {str(n): (sum(index[d] for d in days) if all(d in index for d in days) else None)
            for n in [3,7,14] for days in [[t-timedelta(days=i) for i in range(1,n+1)]]}

def import_series(kind, csv_path, provenance_path, output):
    ctx = context(); provenance = json.loads(Path(provenance_path).read_text())
    for key in ['source_url','product','version','unit','native_crs','spatial_resolution','quality_screening','spatial_aggregation','bbox_wsen','retrieved_at_utc']:
        if key not in provenance or provenance[key] in [None,'']:
            raise ValueError('Missing provenance: '+key)
    if provenance['bbox_wsen'] != ctx['bbox_wsen']:
        raise ValueError('Regional export bounds must exactly match the documented context bbox')
    host=urlsplit(provenance['source_url']).hostname or ''
    if not (host.endswith('.nasa.gov') or host in ['nasa.gov','nsidc.org'] or host.endswith('.nsidc.org')):
        raise ValueError('Expected an official NASA or NSIDC provenance URL')
    expected_unit = 'mm/day' if kind == 'imerg' else 'm3/m3'
    if provenance['unit'] != expected_unit:
        raise ValueError('Expected unit: '+expected_unit)
    with Path(csv_path).open(newline='',encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    observations=[]; seen=set()
    for r in rows:
        # Provenance is mandatory, and each row must be explicitly quality accepted.
        d = date.fromisoformat(r['date']).isoformat(); value=float(r['value'])
        if d in seen: raise ValueError('Duplicate date')
        seen.add(d)
        if not ctx['start'] <= d <= ctx['end']: continue
        if not math.isfinite(value) or value < 0 or (kind=='smap' and value>1): raise ValueError('Invalid measurement')
        if r.get('quality')!='accepted': continue
        if kind=='smap' and SMAP_NOTICE['start'] <= d <= SMAP_NOTICE['end'] and provenance.get('geolocation_reprocessing_verified') is not True:
            continue
        observations.append({'date':d,'value':value,'quality':'accepted'})
    observations.sort(key=lambda r:r['date'])
    result = {'schema_version':1,**ctx,'kind':kind,'status':'available' if observations else 'unavailable','observations':observations,'provenance':provenance,'source_csv_sha256':hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()}
    if kind=='imerg': result['at_nisar_dates']=[{'date':d,'previous_complete_days_mm':aggregate_rain(observations,d)} for d in ctx['nisar_dates']]
    if kind=='smap': result['quality_notice']=SMAP_NOTICE
    save_new(output,result)

def fire_plan(availability, start, end):
    """Prefer standard S-NPP records; explicitly use NRT only outside its archive."""
    spans = {r['data_id']: (date.fromisoformat(r['min_date']), date.fromisoformat(r['max_date']))
             for r in availability if r.get('data_id') in ('VIIRS_SNPP_SP', 'VIIRS_SNPP_NRT')}
    plan=[]
    while start <= end:
        source=next((s for s in ('VIIRS_SNPP_SP','VIIRS_SNPP_NRT') if s in spans and spans[s][0]<=start<=spans[s][1]),None)
        if source is None: raise ValueError('FIRMS availability has a gap in the requested dates; no complete dataset can be written')
        stop=min(end,start+timedelta(days=4),spans[source][1])
        # Avoid querying NRT past the beginning of available standard processing.
        if source.endswith('_NRT') and 'VIIRS_SNPP_SP' in spans and start < spans['VIIRS_SNPP_SP'][0] <= stop:
            stop=spans['VIIRS_SNPP_SP'][0]-timedelta(days=1)
        plan.append((source,start,stop));start=stop+timedelta(days=1)
    return plan

def firms(output, prompt_key=False):
    key=os.environ.get('FIRMS_MAP_KEY')
    if not key and prompt_key:
        from getpass import getpass
        key=getpass('FIRMS MAP_KEY (not echoed or saved): ')
    if not key: raise ValueError('Set FIRMS_MAP_KEY locally. Do not paste it into chat or commit it.')
    if Path(output).exists(): raise FileExistsError('Existing FIRMS output is preserved; review it before replacing')
    ctx=context(); ctx['end']=(date.fromisoformat(ctx['end'])+timedelta(days=7)).isoformat(); bbox=','.join(map(str,ctx['bbox_wsen'])); start=date.fromisoformat(ctx['start']); end=date.fromisoformat(ctx['end']); features=[]; seen=set(); completed=[]
    try:
        body,_,_=read_url(f'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{key}/all')
        availability=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
        plan=fire_plan(availability,start,end)
    except (HTTPError,URLError,TimeoutError,OSError,KeyError,ValueError):
        raise ValueError('Cannot verify FIRMS historical availability; no output written') from None
    for source,start,stop in plan:
        days=(stop-start).days+1
        url=f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}/{start.isoformat()}'
        try: body,_,_=read_url(url)
        except (HTTPError,URLError,TimeoutError,OSError): raise ValueError('FIRMS retrieval failed; check your key and historical product availability. No partial output written.') from None
        reader=csv.DictReader(io.StringIO(body.decode()))
        if not {'latitude','longitude','acq_date','acq_time','confidence'}.issubset(reader.fieldnames or []): raise ValueError('FIRMS returned an error or unexpected schema; no output written')
        for row in reader:
            lon,lat=float(row['longitude']),float(row['latitude']); d=date.fromisoformat(row['acq_date']).isoformat(); clock=str(row['acq_time']).zfill(4)
            if not (ctx['bbox_wsen'][0]<=lon<=ctx['bbox_wsen'][2] and ctx['bbox_wsen'][1]<=lat<=ctx['bbox_wsen'][3]) or not start<=date.fromisoformat(d)<start+timedelta(days=days): raise ValueError('FIRMS row outside requested region or time interval')
            timestamp=datetime.strptime(d+' '+clock,'%Y-%m-%d %H%M').replace(tzinfo=timezone.utc).isoformat(); token=(lon,lat,timestamp,row.get('satellite'))
            if token in seen: continue
            seen.add(token)
            frp=float(row['frp']) if row.get('frp') else None
            if frp is not None and (not math.isfinite(frp) or frp<0): raise ValueError('Invalid FIRMS FRP')
            props={k:row.get(k) for k in ['confidence','satellite','instrument','daynight','version']}; props.update(date=d,acquired_at_utc=timestamp,frp_mw=frp,source=source,processing='standard' if source.endswith('_SP') else 'near-real-time')
            features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},'properties':props})
        completed.append({'source':source,'start':start.isoformat(),'end':stop.isoformat()})
    provenance=dict(SOURCES['firms'],name='NASA FIRMS VIIRS S-NPP: standard archive + labeled near-real-time records',processing_note='Standard processing is preferred where available. Later dates use NRT explicitly; revisions and processing differences may affect comparisons.',retrieved_at_utc=datetime.now(timezone.utc).isoformat())
    save_new(output,{'type':'FeatureCollection','schema_version':1,**ctx,'status':'available','coverage_complete':True,'queried_intervals':completed,'provenance':provenance,'features':features})

def register_files(files, output):
    audit=json.loads((WEB/'data/environment/access.json').read_text())
    for kind, filename in files.items():
        if not filename: continue
        file=Path(filename).resolve()
        if file.parent != (WEB/'data/environment').resolve() or file.name != {'imerg':'imerg.json','smap':'smap.json','firms':'firms.geojson'}[kind]:
            raise ValueError('Register only the expected imported file inside web/data/environment')
        d=json.loads(file.read_text())
        if d.get('schema_version')!=1 or d.get('status')!='available':raise ValueError('Dataset has no available observations')
        if kind!='firms' and (d.get('kind')!=kind or not d.get('observations')):raise ValueError('Missing series or kind mismatch')
        if kind=='firms' and (d.get('type')!='FeatureCollection' or d.get('coverage_complete') is not True):raise ValueError('Incomplete FIRMS coverage')
        audit['datasets'][kind].update(file=file.name,status='available',registered_file_sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    audit['registered_at_utc']=datetime.now(timezone.utc).isoformat()
    save_new(output,audit)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('probe'); q.add_argument('--out',required=True)
    q=sub.add_parser('firms'); q.add_argument('--out',required=True); q.add_argument('--prompt-key',action='store_true')
    q=sub.add_parser('import');q.add_argument('kind',choices=['imerg','smap']);q.add_argument('--csv',required=True);q.add_argument('--provenance',required=True);q.add_argument('--out',required=True)
    q=sub.add_parser('register');q.add_argument('--imerg');q.add_argument('--smap');q.add_argument('--firms');q.add_argument('--out',required=True)
    a=p.parse_args()
    if a.command=='probe':probe(a.out)
    elif a.command=='firms':firms(a.out,a.prompt_key)
    elif a.command=='register':register_files({k:getattr(a,k) for k in ['imerg','smap','firms']},a.out)
    else:import_series(a.kind,a.csv,a.provenance,a.out)
