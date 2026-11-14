"""Open one NISAR GCOV granule lazily and print a truncated datatree (no full download)."""
import sys, time
import earthaccess, xarray as xr

def open_tree(url):
    earthaccess.login(strategy="netrc")
    f = earthaccess.open([url])[0]
    return xr.open_datatree(f, engine="h5netcdf", phony_dims="access"), f

if __name__ == "__main__":
    t = time.time()
    tree, _ = open_tree(sys.argv[1])
    print(f"opened in {time.time()-t:.1f}s")
    for node in tree.subtree:
        vs = {k: (v.shape, str(v.dtype)) for k, v in node.ds.data_vars.items()}
        big = {k: s for k, s in vs.items() if len(s[0]) >= 2}
        if big or node.path.count("/") <= 4:
            print(node.path, "| dims", dict(node.ds.sizes) if len(node.ds.sizes) < 6 else "...", "|", big or "")
