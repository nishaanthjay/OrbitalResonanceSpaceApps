"""Synthetic inputs in temporary files only; no measurements are written into web/data."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from environment_data import aggregate_rain, context, import_series, save_new, fire_plan
from datetime import date

class EnvironmentTests(unittest.TestCase):
    def test_fire_archive_boundary_and_missing_coverage(self):
        availability=[{'data_id':'VIIRS_SNPP_SP','min_date':'2012-01-20','max_date':'2026-07-31'}, {'data_id':'VIIRS_SNPP_NRT','min_date':'2026-08-01','max_date':'2026-11-02'}]
        plan=fire_plan(availability,date(2026,7,29),date(2026,8,4))
        self.assertEqual(plan,[('VIIRS_SNPP_SP',date(2026,7,29),date(2026,7,31)),('VIIRS_SNPP_NRT',date(2026,8,1),date(2026,8,4))])
        with self.assertRaises(ValueError):fire_plan(availability,date(2026,11,1),date(2026,11,4))
    def test_rain_complete_window(self):
        rows=[{'date':f'2026-07-{d:02}','value':1} for d in range(1,15)]
        self.assertEqual(aggregate_rain(rows,'2026-07-15'),{'3':3,'7':7,'14':14})
        self.assertIsNone(aggregate_rain(rows[1:],'2026-07-15')['14'])
    def test_bad_daily_observations(self):
        for rows in [[{'date':'2026-07-01','value':-1}],[{'date':'2026-07-01','value':'nan'}],[{'date':'2026-07-01','value':1}]*2]:
            with self.assertRaises(ValueError):aggregate_rain(rows,'2026-07-15')
    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'out.json';save_new(p,{'test':True})
            with self.assertRaises(FileExistsError):save_new(p,{'test':False})
            self.assertEqual(json.loads(p.read_text()),{'test':True})
    def test_provenance_and_smap_issue_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);csvfile=tmp/'test.csv';csvfile.write_text('date,value,quality\n2026-07-08,0.3,accepted\n2026-08-13,0.25,accepted\n2026-08-25,0.27,rejected\n')
            provenance={'source_url':'https://nsidc.org/data/spl4smgp/versions/8','product':'SPL4SMGP','version':'008','unit':'m3/m3','native_crs':'test-only CRS descriptor','spatial_resolution':'9 km','quality_screening':'test-only accepted flags','spatial_aggregation':'test-only mean','bbox_wsen':context()['bbox_wsen'],'retrieved_at_utc':'2026-11-15T00:00:00Z'}
            p=tmp/'provenance.json';p.write_text(json.dumps(provenance));out=tmp/'output.json';import_series('smap',csvfile,p,out)
            self.assertEqual([r['date'] for r in json.loads(out.read_text())['observations']],['2026-08-13'])
            provenance.pop('quality_screening');p.write_text(json.dumps(provenance))
            with self.assertRaises(ValueError):import_series('smap',csvfile,p,tmp/'bad.json')

if __name__=='__main__':unittest.main()
