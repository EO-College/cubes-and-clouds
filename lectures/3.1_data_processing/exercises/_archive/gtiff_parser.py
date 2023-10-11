import os
import rioxarray
from dateutil import parser
import pandas as pd
import xarray as xr
import requests
from enum import Enum


class CustomMimeType(Enum):
    TIFF = "tiff"
    ZARR = "zarr"
    NETCDF = "netcdf"


SUPPORTED_FORMATS = [
    CustomMimeType.TIFF.value,
    CustomMimeType.ZARR.value,
    CustomMimeType.NETCDF.value,
]


parsed_output_file_name = {
    CustomMimeType.TIFF: {"name": "output", "ext": ".tif"},
    CustomMimeType.ZARR: {"name": "output", "ext": ".zarr"},
    CustomMimeType.NETCDF: {"name": "output", "ext": ".nc"},
}


# assume it's only 1 time and 1 bands dimension
def check_dimensions(time_dimensions, bands_dimensions):
    if len(time_dimensions) == 0:
        raise Exception("No time dimensions exist. Only 1 time dimension is supported.")

    if len(time_dimensions) > 1:
        raise Exception("More than 1 time dimension exist. Only 1 time dimension is supported.")

    if len(bands_dimensions) == 0:
        raise Exception("No bands dimensions exist. Only 1 bands dimension is supported.")

    if len(bands_dimensions) > 1:
        raise Exception("More than 1 bands dimension exist. Only 1 bands dimension is supported.")


def get_timestamps_arrays(datacube_time_as_bands, time_dimensions, bands_dimensions, output_format):
    num_of_img_bands = len(datacube_time_as_bands["band"])
    num_of_bands_dimension = len(bands_dimensions[0]["labels"])

    list_of_timestamps = []
    list_of_timestamp_arrays = []

    for i in range(0, num_of_img_bands, num_of_bands_dimension):
        date = time_dimensions[0]["labels"][int(i / num_of_bands_dimension)]
        timestamp_array = datacube_time_as_bands[i : i + num_of_bands_dimension]

        if output_format in [CustomMimeType.NETCDF.value, CustomMimeType.ZARR.value]:
            pandas_time = pd.to_datetime(parser.parse(date))
            timestamp_array = timestamp_array.assign_coords(band=bands_dimensions[0]["labels"])
            timestamp_array = timestamp_array.assign_coords(t=pandas_time)
            timestamp_array = timestamp_array.expand_dims(dim="t")

        list_of_timestamps.append(date)
        list_of_timestamp_arrays.append(timestamp_array)

    return list_of_timestamps, list_of_timestamp_arrays


def save_as_gtiff(list_of_timestamps, list_of_timestamp_arrays, output_dir, output_name):
    output_file_paths = []
    for array, date in zip(list_of_timestamp_arrays, list_of_timestamps):
        file_name = f"{output_name['name']}_{date}{output_name['ext']}"
        file_path = os.path.join(output_dir, file_name)
        output_file_paths.append(file_path)

        array.rio.to_raster(
            file_path,
            tiled=True,  # GDAL: By default striped TIFF files are created. This option can be used to force creation of tiled TIFF files.
            windowed=True,  # rioxarray: read & write one window at a time
        )
    return output_file_paths


def save_as_netcdf(list_of_timestamp_arrays, output_dir, output_name):
    datacube_with_time_dimension = xr.combine_by_coords(list_of_timestamp_arrays)
    output_file_path = os.path.join(output_dir, f"{output_name['name']}{output_name['ext']}")
    datacube_with_time_dimension.to_netcdf(output_file_path)
    return [output_file_path]


def save_as_zarr(list_of_timestamp_arrays, output_dir, output_name):
    datacube_with_time_dimension = xr.combine_by_coords(list_of_timestamp_arrays)
    output_file_path = os.path.join(output_dir, f"{output_name['name']}{output_name['ext']}")
    datacube_with_time_dimension.to_zarr(output_file_path)
    return [output_file_path]


def parse_multitemporal_gtiff_to_format(input_tiff, input_metadata, output_dir, output_format):
    datacube_time_as_bands = rioxarray.open_rasterio(input_tiff)
    datacube_metadata = requests.get(input_metadata).json()

    time_dimensions = [dim for dim in datacube_metadata["outputDimensions"] if dim["type"] == "temporal"]
    bands_dimensions = [dim for dim in datacube_metadata["outputDimensions"] if dim["type"] == "bands"]

    # mock a bands dimension (with 1 band) if it's not present in the data
    # e.g. save_result process right after ndvi process which doesn't have a target band set
    if len(bands_dimensions) == 0:
        bands_dimensions = [{"name": "bands", "type": "bands", "labels": ["results"]}]

    check_dimensions(time_dimensions, bands_dimensions)

    list_of_timestamps, list_of_timestamp_arrays = get_timestamps_arrays(
        datacube_time_as_bands, time_dimensions, bands_dimensions, output_format
    )

    if output_format == CustomMimeType.TIFF.value:
        output_name = parsed_output_file_name[CustomMimeType.TIFF]
        return save_as_gtiff(list_of_timestamps, list_of_timestamp_arrays, output_dir, output_name)

    if output_format == CustomMimeType.NETCDF.value:
        output_name = parsed_output_file_name[CustomMimeType.NETCDF]
        return save_as_netcdf(list_of_timestamp_arrays, output_dir, output_name)

    if output_format == CustomMimeType.ZARR.value:
        output_name = parsed_output_file_name[CustomMimeType.ZARR]
        return save_as_zarr(list_of_timestamp_arrays, output_dir, output_name)

    raise Exception(f"Parsing to format {output_format} is not supported. Supported formats: {str(SUPPORTED_FORMATS)}")


# URL containing "default.tif" from a response to "/jobs/{job_id}/results"
input_tiff = ""

# URL containing "userdata.json" from a response to "/jobs/{job_id}/results"
input_metadata = ""

# folder where the output files will be put
output_dir = "."

# output format
output_format = "netcdf"

output_file_paths = parse_multitemporal_gtiff_to_format(input_tiff, input_metadata, output_dir, output_format)

print("output_file_paths:", output_file_paths)
