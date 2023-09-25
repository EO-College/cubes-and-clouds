import xarray
import rioxarray

def open_tiff(input_tiff):
    img = rioxarray.open_rasterio(input_tiff)
    print(img)

def open_netcdf(input_netcdf):
    xds = xarray.open_dataset(input_netcdf, decode_coords="all")
    print(xds)

def open_zarr(input_zarr):
    xds = xarray.open_zarr(input_zarr, decode_coords="all")
    print(xds)