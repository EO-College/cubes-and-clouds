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

from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay


# pystac libraries
import pystac
from pystac.utils import str_to_datetime

# Import rio_stac extensions
from rio_stac.stac import PROJECTION_EXT_VERSION, RASTER_EXT_VERSION, EO_EXT_VERSION

# Import rio_stac methods
from rio_stac.stac import (
    get_dataset_geom,
    get_projection_info,
    get_raster_info,
    get_eobands_info,
    bbox_to_geom,
)


def validation_metrics(df):
    cf_init = np.array([[np.nan, np.nan], [np.nan, np.nan]])

    acc = accuracy_score(df.snow_presence, df.cube_snow)
    cf = confusion_matrix(df.snow_presence, df.cube_snow)
    
    if len(cf)==1:
        cf_init[0][0] = cf[0][0]
    else:
        cf_init = cf
    
    return acc, cf_init

def calculate_sca(conn, bbox, temporal_extent):
    s2_cube = conn.load_collection(
        'SENTINEL2_L2A',
        spatial_extent={'west':bbox[0],
                        'east':bbox[2],
                        'south':bbox[1],
                        'north':bbox[3],
                        'crs':4326
                       },
        bands=['B03', 'B11'],
        temporal_extent=temporal_extent
    )
    
    # compute ndsi and snowmap
    green = s2_cube.band("B03")
    swir = s2_cube.band("B11")
    ndsi = (green - swir) / (green + swir)
    
    snowmap = ( ndsi > 0.4 ) * 1.0
    
    cm_cube = conn.load_collection(
        'SENTINEL2_L2A',
        spatial_extent={'west':bbox[0],
                        'east':bbox[2],
                        'south':bbox[1],
                        'north':bbox[3],
                        'crs':4326
                       },
        bands=['SCL'],
        temporal_extent=temporal_extent
    )
    # mask out cloud using SCL
    # reference: https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/level-2a/algorithm-overview
    scl_band = cm_cube.band("SCL")
    cloud_mask = ( (scl_band == 8) | (scl_band == 9) | (scl_band == 3) ) * 1.0
    snowmap_cloudfree = snowmap.mask(cloud_mask)
    
    return snowmap_cloudfree

def format_date(df):
    from datetime import datetime 
    if df.Date:
        date_obj = datetime.strptime(df.Date, '%d.%m.%y')        
        return date_obj.strftime('%Y-%m-%d')

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
    df = df.dropna()
    # assign 0 to cloudy pixels -- assumes no-snow
    # df["cube_snow"] = np.where(df["cube_snow"] == np.nan, 0, np.where(df["cube_snow"]==1, 1, 0))
    
    return df