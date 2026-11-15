"""Native reader tests use temporary synthetic files only."""
from datetime import datetime,timezone
import numpy as np
import pytest
from environment_native import daily_soil,soil_region,rain_region,read_stream,open_native_stream

def test_remote_reader_disables_background_prefetch_and_bounds_request_time(tmp_path):
    import h5py
    path=tmp_path/'synthetic-remote.h5'
    with h5py.File(path,'w') as f:f['value']=[42]
    calls=[]
    class FS:
        def open(self,url,mode,**kwargs):
            calls.append(kwargs);return path.open(mode)
    class Access:
        def get_fsspec_https_session(self):return FS()
    assert open_native_stream(Access(),'https://example.invalid/test',lambda f:int(f['value'][0]))==42
    assert calls==[{'block_size':262144,'cache_type':'blockcache','timeout':60}]

def test_stream_wrapper_uses_underlying_context_manager(tmp_path):
    import h5py
    path=tmp_path/'synthetic-stream.h5'
    with h5py.File(path,'w') as f:f['value']=[42]
    class Wrapper:
        def __init__(self,f):self.f=f
        def __getattr__(self,name):return getattr(self.f,name)
    fp=Wrapper(path.open('rb'))
    assert read_stream(fp,lambda f:int(f['value'][0]))==42
    assert fp.f.closed

def test_soil_day_requires_eight_unique_intervals_and_excludes_issue_dates():
    rows=[{'timestamp':f'2026-08-13T{h:02}:30:00+00:00','value':0.2,'native_cells':48} for h in range(1,24,3)]
    assert daily_soil(rows)[0]['value']==pytest.approx(0.2)
    assert daily_soil(rows[:-1])==[]
    with pytest.raises(ValueError):daily_soil(rows+[rows[0]])
    assert daily_soil([dict(r,timestamp=r['timestamp'].replace('08-13','07-20')) for r in rows])==[]

def test_native_soil_fill_and_frozen_screening(tmp_path):
    import h5py
    path=tmp_path/'synthetic.h5'
    with h5py.File(path,'w') as f:
        f['cell_lat']=np.array([[-8.,-8.]])
        f['cell_lon']=np.array([[-54.8,-54.6]])
        ds=f.create_dataset('Geophysical_Data/sm_surface',data=[[0.2,0.4]])
        ds.attrs['units']='m3 m-3';ds.attrs['valid_min']=0.;ds.attrs['valid_max']=0.9;ds.attrs['_FillValue']=-9999.
        f['Geophysical_Data/soil_temp_layer1']=[[290.,290.]]
        f['Geophysical_Data/land_fraction_snow_covered']=[[1e-8,3e-8]]
        result,_=soil_region(f,[-55,-9,-54,-7]);assert result['value']==pytest.approx(0.3)
        f['Geophysical_Data/soil_temp_layer1'][0,0]=270.
        with pytest.raises(ValueError):soil_region(f,[-55,-9,-54,-7])

def test_native_rain_coordinate_order_units_and_missing_data(tmp_path):
    import h5py
    with h5py.File(tmp_path/'synthetic.nc4','w') as f:
        f['lat']=[-8.2,-8.1];f['lon']=[-54.8,-54.7,-54.6]
        ds=f.create_dataset('precipitation',data=np.full((1,3,2),4.))
        ds.attrs['units']='mm/day';ds.attrs['_FillValue']=-9999.
        assert rain_region(f,[-55,-9,-54,-7])['value']==pytest.approx(4.)
        ds[0,0,0]=-9999.
        with pytest.raises(ValueError):rain_region(f,[-55,-9,-54,-7])
