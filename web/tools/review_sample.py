"""Proposed 30-point human-review packet. Writes a NEW, non-served output directory only.

Requires Pillow for the existing lossless display rasters. Uses no human/AI labels.
Independent validation owner approval is required before scoring or replacing results.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
from PIL import Image
from shapely.geometry import shape, Point

WEB=Path(__file__).resolve().parents[1]

def generate(out,seed=20261115):
    out=Path(out).resolve()
    if out.is_relative_to(WEB): raise ValueError('Review key must never be saved under the public web directory')
    out.mkdir(parents=True,exist_ok=False)
    big=WEB/'data/explore/big';meta=json.loads((big/'big.json').read_text());fc=json.loads((big/'lost.geojson').read_text());rng=random.Random(seed)
    image_paths=[big/file for file in meta['layers']['forest']]
    images=[Image.open(p).convert('RGBA') for p in image_paths]
    if any(im.size!=images[0].size for im in images): raise ValueError('Mismatched forest grids')
    w,h=images[0].size
    if [w,h]!=[meta['grid']['width'],meta['grid']['height']]:raise ValueError('Grid metadata mismatch')
    forest=tuple(bytes.fromhex(meta['colors']['forest'][1:]))+(255,)
    buffers=[list(getattr(im,'get_flattened_data',im.getdata)()) for im in images];b=meta['grid']['bounds'];original=meta['original_window_bbox']
    def coord(i):
        col,row=i%w,i//w;x=b[0]+(col+.5)*(b[2]-b[0])/w;y=b[3]-(row+.5)*(b[3]-b[1])/h
        return [x/6378137*180/math.pi,(2*math.atan(math.exp(y/6378137))-math.pi/2)*180/math.pi]
    def excluded(p):return original[0]<=p[0]<=original[2] and original[1]<=p[1]<=original[3]
    stable=[i for i in range(w*h) if all(buf[i]==forest for buf in buffers) and not excluded(coord(i))]
    groups={k:[f for f in fc['features'] if f['properties']['category']==k and not f['properties']['in_original_window']] for k in ['alert_supported','radar_only_unconfirmed']}
    rows=[];pop={k:len(v) for k,v in groups.items()};pop['stable_radar_display_pixel']=len(stable)
    for group,features in groups.items():
        for f in rng.sample(features,10):
            p=f['properties'];polygon=shape(f['geometry']);west,south,east,north=polygon.bounds
            for attempt in range(10000):
                point=Point(rng.uniform(west,east),rng.uniform(south,north))
                if polygon.contains(point):break
            else:raise ValueError('Could not sample inside polygon')
            rows.append({'lon':point.x,'lat':point.y,'stratum':group,'patch_id':p['id'],'population':len(features),'sample_size':10})
    for index in rng.sample(stable,10):
        lon,lat=coord(index);rows.append({'lon':lon,'lat':lat,'stratum':'stable_radar_display_pixel','pixel_index':index,'population':len(stable),'sample_size':10})
    rng.shuffle(rows)
    optical=json.loads((WEB/'data/explore/optical/optical.json').read_text());before=min(p['date'] for p in optical['passes']);after=max(p['date'] for p in optical['passes'])
    with (out/'blind_review.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['point_id','lon','lat','before_date','after_date','label','reviewer','notes']);writer.writeheader()
        for i,r in enumerate(rows,1):r['point_id']=f'R{i:02}';writer.writerow({'point_id':r['point_id'],'lon':round(r['lon'],6),'lat':round(r['lat'],6),'before_date':before,'after_date':after,'label':'','reviewer':'','notes':''})
    key={'status':'proposal_not_scored','seed':seed,'unit_warning':'Flagged strata sample patches; controls sample stable radar display pixels. Not interchangeable independent units. Do not compute population recall from this case-control sample.','exclusion':'Original 20 km development window excluded by centroid/pixel centre. The wider 60 km region is previously evaluated; this is not a new held-out region.','population_by_stratum':pop,'sample':rows,'source_sha256':{str(p.relative_to(WEB)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [big/'big.json',big/'lost.geojson',*image_paths]}}
    (out/'PRIVATE-review-key.json').write_text(json.dumps(key,indent=2)+'\n',encoding='utf-8')
    print(f'Generated {len(rows)} unlabeled points in {out}')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--seed',type=int,default=20261115);a=p.parse_args();generate(a.out,a.seed)
