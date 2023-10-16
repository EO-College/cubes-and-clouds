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
    
    # assign 0 to cloudy pixels -- assumes no-snow
    df["cube_snow"] = np.where(df["cube_snow"] == np.nan, 0, np.where(df["cube_snow"]==1, 1, 0))
    
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

def generate_stac(assets,
                  media_type,
                  id="Snow_map",
                  collection=None,
                  collection_url=None,
                  input_datetime=None,
                  properties = {}):
    "generates stac item or collection from a list of specified geospatial data assets"
                       
    extensions =[
        f"https://stac-extensions.github.io/projection/{PROJECTION_EXT_VERSION}/schema.json",
        f"https://stac-extensions.github.io/raster/{RASTER_EXT_VERSION}/schema.json",
        f"https://stac-extensions.github.io/eo/{EO_EXT_VERSION}/schema.json"
    ]
                  
    bboxes = []
    pystac_assets = []
    img_datetimes = []

    for asset in assets:
        with rasterio.open(asset["path"]) as src_dst:
            # Get BBOX and Footprint
            dataset_geom = get_dataset_geom(src_dst, densify_pts=0, precision=-1)
            bboxes.append(dataset_geom["bbox"])

            if "start_datetime" not in properties and "end_datetime" not in properties:
                # Try to get datetime from https://gdal.org/user/raster_data_model.html#imagery-domain-remote-sensing
                dst_date = src_dst.get_tag_item("ACQUISITIONDATETIME", "IMAGERY")
                dst_datetime = str_to_datetime(dst_date) if dst_date else None
                if dst_datetime:
                    img_datetimes.append(dst_datetime)

            proj_info = {
                f"proj:{name}": value
                for name, value in get_projection_info(src_dst).items()
            }

            raster_info = {
                "raster:bands": get_raster_info(src_dst, max_size=1024)
            }

            eo_info = {}
            eo_info = {"eo:bands": get_eobands_info(src_dst)}
            cloudcover = src_dst.get_tag_item("CLOUDCOVER", "IMAGERY")
            if cloudcover is not None:
                properties.update({"eo:cloud_cover": int(cloudcover)})

            pystac_assets.append(
                (
                    asset["name"], 
                    pystac.Asset(
                        href=asset["href"] or src_dst.name,
                        media_type=media_type,
                        extra_fields={
                            **proj_info,
                            **raster_info, 
                            **eo_info
                        },
                        roles=asset["role"],
                    ),
                )
            )

    if img_datetimes and not input_datetime:
        input_datetime = img_datetimes[0]

    input_datetime = input_datetime or datetime.datetime.utcnow()    

    minx, miny, maxx, maxy = zip(*bboxes)
    bbox = [min(minx), min(miny), max(maxx), max(maxy)]

    # item
    item = pystac.Item(
        id=id,
        geometry=bbox_to_geom(bbox),
        bbox=bbox,
        collection=collection,
        stac_extensions=extensions,
        datetime=input_datetime,
        properties=properties,
    )

    # creating collection requires to specify the link
    if collection:
        item.add_link(
            pystac.Link(
                pystac.RelType.COLLECTION,
                collection_url or collection,
                media_type=pystac.MediaType.JSON,
            )
        )

    for key, asset in pystac_assets:
        item.add_asset(key=key, asset=asset)
    
    return item
