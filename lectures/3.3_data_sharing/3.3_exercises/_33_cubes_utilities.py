""" Contains utility functions used for different exercises within the EO 
Cubes and Clouds MOOC to enhance modularity, reproducibility of code"""

import math
import datetime

import numpy as np
import pandas as pd

# geospatial libraries
import geopandas as gpd
import rasterio
import shapely
from shapely.geometry import Polygon


# pystac libraries
import pystac
from pystac.utils import str_to_datetime
from osgeo import gdal


def calculate_sca(conn, bbox, temporal_extent):
    s2 = conn.load_collection(
        'SENTINEL2_L2A',
        spatial_extent={'west':bbox[0],
                        'east':bbox[2],
                        'south':bbox[1],
                        'north':bbox[3],
                        'crs':4326
                       },
        bands=['B03', 'B11', 'SCL'],
        temporal_extent=temporal_extent
    )
    
    # compute ndsi and snowmap
    green = s2.band("B03")
    swir = s2.band("B11")
    ndsi = (green - swir) / (green + swir)
    
    snowmap = ( ndsi > 0.4 ) * 1.0
    
    # mask out cloud using SCL
    # reference: https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/level-2a/algorithm-overview
    scl_band = s2.band("SCL")
    cloud_mask = ( (scl_band == 8) | (scl_band == 9) | (scl_band == 3) ) * 1.0
    snowmap_cloudfree = snowmap.mask(cloud_mask)
    
    return snowmap_cloudfree

def station_temporal_filter(station_daily_df,
                    station_meta_df,
                    start_date='2018-02-10',
                    end_date='2018-06-30'):
    
    # merge and filter to get lon/lat and start and end date
    full_station_df = pd.merge(station_daily_df,
                            station_meta_df,
                            how="inner",
                            on=["Provider", "Name"]
                           ).set_index(station_daily_df.Date)
    
    full_station_df = full_station_df.drop(["HN_year_start", "HN_year_end", 
                                            "HS_year_start", "HS_year_end"], axis=1)
    full_station_df = full_station_df.sort_index(ascending=True)
    full_station_df = full_station_df.loc[start_date:end_date]
    
    # convert lat/long to geometries
    snow_stations = gpd.GeoDataFrame(
        full_station_df,
        geometry=gpd.points_from_xy(full_station_df.Longitude, full_station_df.Latitude),
        crs="EPSG:4326"
    )
    return snow_stations

def station_spatial_filter(snow_stations, catchment_area):
    # select stations within catchment area
    catchment_stations = gpd.sjoin(snow_stations, catchment_area, op='within')
    
    # remove unneccessary columns
    station_columns = ['Provider', 'Name', 'HN', 'HS', 'HN_after_qc', 'HS_after_qc',
       'HS_after_gapfill', 'Longitude', 'Latitude', 'Elevation', 'geometry']
    catchment_stations = catchment_stations[station_columns]
    return catchment_stations

def binarize_snow(df):
    # binarize snow presence at station level. 
    '''
    0:: implies no snow
    1:: implies snow presence
    '''
    
    if df["HS_after_gapfill"] > 0:
        return 1
    elif df["HS_after_gapfill"] <= 0:
        return 0
    else:
        return 0


def assign_site_snow(df, snow_val):
    # assign site snow values to the datacube output for validation
    df["cube_snow"] = snow_val
    df = df.set_index("id")
    df = df.sort_values(axis=0, by="id")
    df.dropna()
    
    # assign 0 to cloudy pixels -- assumes no-snow
    # df["cube_snow"] = np.where(df["cube_snow"] == np.nan, 0, np.where(df["cube_snow"]==1, 1, 0))
    
    return df

def create_bounding_box(latitude, longitude, distance_km):
    # create a bounding box around a point
    
    # Radius of the Earth in kilometers
    earth_radius_km = 6371

    # Convert latitude and longitude from degrees to radians
    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)

    # Calculate the angular distance covered by the given distance_km
    angular_distance = distance_km / earth_radius_km

    # Calculate the latitude and longitude offsets
    lat_offset = math.degrees(angular_distance)
    lon_offset = math.degrees(angular_distance / math.cos(lat_rad))

    # Calculate the coordinates of the southwest and northeast corners
    sw_lat = latitude - lat_offset
    sw_lon = longitude - lon_offset
    ne_lat = latitude + lat_offset
    ne_lon = longitude + lon_offset
    
    return (sw_lat, sw_lon, ne_lat, ne_lon)

def visualize_bbox(map_layer, bbox):
    # Create polygon from lists of points
    x = [bbox[0], bbox[0], bbox[2], bbox[2], bbox[0]]
    y = [bbox[1], bbox[3], bbox[3], bbox[1], bbox[1]]
    poly = Polygon(zip(x,y))
    gs = gpd.GeoSeries.from_wkt([str(poly)])
    gdf = gpd.GeoDataFrame({"col1": ["bbox"]}, geometry=gs, crs=4326)
    #visualize generated bounding box
    return map_layer.add_gdf(gdf)


def raster_rescale_stats(in_data_path, stat_data_path):
    # computes raster statistics
    ds = gdal.Open(in_data_path, gdal.GA_Update)
    n_of_bands = ds.RasterCount
    
    for band in range(n_of_bands):
        ds.GetRasterBand(band+1).ComputeStatistics(0)
        ds.GetRasterBand(band+1).SetNoDataValue(np.nan)
    
    # save raster statistics
    fileformat = "GTiff"
    driver = gdal.GetDriverByName(fileformat)
    metadata = driver.GetMetadata()
    if metadata.get(gdal.DCAP_CREATE) == "YES":
        print("Driver {} supports Create() method.".format(fileformat))
    
    dst_ds = driver.CreateCopy(stat_data_path, ds, strict=0)
    dst_ds = None
    ds = None
    
    return None


def extract_metadata_geometry(stac_collection):
    meta_bbox = stac_collection["providers"][0]['processing:expression'][0]['expression']['loadcollection1']['arguments']['spatial_extent']
    min_x = meta_bbox["west"]
    min_y = meta_bbox["south"]
    max_x = meta_bbox["east"]
    max_y = meta_bbox["north"]
    
    bbox = [min_x, min_y, max_x, max_y]
    
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y]
        ]]
    }
    
    return bbox, geometry