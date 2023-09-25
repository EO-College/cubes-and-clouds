# Import necessary libraries
from time import time
import rasterio
import numpy as np
import openeo
import xarray as xr
import rioxarray
from ipyleaflet import (
    Map,
    Marker,
    TileLayer, ImageOverlay,
    Polygon, Rectangle,
    GeoJSON,
    DrawControl,
    LayersControl,
    WidgetControl,
    basemaps,
    FullScreenControl
)
from ipywidgets import Output, FloatSlider
from traitlets import link
import shapely.geometry
import requests
import os
from tqdm import tqdm
import zipfile
import xarray_leaflet
from xarray_leaflet.transform import passthrough
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from bqplot import Lines, Figure, LinearScale, DateScale, Axis, Scatter
import bqplot.pyplot as bqplt
from datetime import datetime
import json
from openeo.processes import if_, neq,array_element
import hvplot.xarray
import warnings
warnings.filterwarnings("ignore")

class openeoMap:
    def __init__(self,center,zoom):
        self.map = Map(center=center, zoom=zoom, scroll_wheel_zoom=True, interpolation='nearest')
        self.bbox = []
        self.point_coords = []
        self.figure = None
        self.figure_widget = None
        feature_collection = {
            'type': 'FeatureCollection',
            'features': []
        }

        draw = DrawControl(
            circlemarker={}, polyline={}, polygon={},
            marker= {"shapeOptions": {
                       "original": {},
                       "editing": {},
            }},
            rectangle = {"shapeOptions": {
                       "original": {},
                       "editing": {},
            }})

        self.map.add_control(draw)
        def handle_draw(target, action, geo_json):
            feature_collection['features'] = []
            feature_collection['features'].append(geo_json)
            if feature_collection['features'][0]['geometry']['type'] == 'Point':
                self.point_coords = feature_collection['features'][0]['geometry']['coordinates']
            else:
                coords = feature_collection['features'][0]['geometry']['coordinates'][0]
                polygon = shapely.geometry.Polygon(coords)
                self.bbox = polygon.bounds
        
        layers_control = LayersControl(position='topright')
        self.map.add_control(layers_control)
        self.map.add_control(FullScreenControl())
        draw.on_draw(handle_draw)
    
    def getBbox(self):
        if(len(self.bbox) == 0):
            mapBox = self.map.bounds     
            return [ mapBox[0][1],mapBox[0][0],mapBox[1][1],mapBox[1][0]]
        else:
            return self.bbox
           
def addLayer(inMap,path,name,clip=[0,0.8],bands=None):
    #Check the filetype: netcdf or geotiff
    if path.split('.')[-1] == 'nc':
        da = xr.open_dataset(path)
        if 't' in da.dims:
            da = da.drop('t').squeeze('t').to_array().astype(np.float32)
        elif 'time' in da.dims:
            da = da.drop('time').squeeze('time').to_array().astype(np.float32)
        else:
            da = da.to_array().astype(np.float32)
        if 'variable' in da.dims and 'bands' in da.dims:
            da = da.drop('variable').squeeze('variable').rename({'bands':'variable'})
    else:
        da = xr.open_rasterio(path)
        if 't' in da.dims:
            da = da.rename({'band':'variable'}).drop('t').squeeze('t').astype(np.float32)
        else:
            da = da.rename({'band':'variable'}).astype(np.float32)
    rds4326 = da.rio.reproject("epsg:4326")
    rds4326.name = name
    rds4326 = rds4326.rio.write_crs(4326)  # WGS 84
    if bands is not None:
        rds4326 = rds4326.loc[dict(variable=bands)]
    opacity_slider = FloatSlider(description=name + ' opacity:', min=0, max=1, value=1)
    def set_opacity(change):
        l.opacity = change['new']
    if(len(rds4326.variable)==3):
        rds4326 = rds4326.clip(clip[0],clip[1])/clip[1]*255
        rds4326 = rds4326.fillna(0).rio.write_nodata(0)
        rds4326 = rds4326.chunk((1000, 1000))
        l = rds4326.leaflet.plot(inMap.map, rgb_dim='variable')
 
        opacity_slider.observe(set_opacity, names='value')
        slider_control = WidgetControl(widget=opacity_slider, position='bottomleft')
        inMap.map.add_control(slider_control)
    elif(len(rds4326.variable)==1):
        rds4326 = rds4326[0]
        rds4326 = rds4326.clip(clip[0],clip[1])
        rds4326 = rds4326.fillna(0).rio.write_nodata(0)
        rds4326 = rds4326.chunk((1000, 1000))
        cmap = plt.cm.get_cmap('Greys_r')
        l = rds4326.leaflet.plot(inMap.map,colormap=cmap)
        def set_opacity(change):
            l.opacity = change['new']

        opacity_slider.observe(set_opacity, names='value')
        slider_control = WidgetControl(widget=opacity_slider, position='bottomleft')
        inMap.map.add_control(slider_control)
    else:
        rds4326 = rds4326[0]
        rds4326 = rds4326.fillna(0).rio.write_nodata(0)
        rds4326 = rds4326.chunk((1000, 1000))
        rds4326 = rds4326.clip(clip[0],clip[1])
        cmap = plt.cm.get_cmap('Greys_r')
        l = rds4326.leaflet.plot(inMap.map,colormap=cmap)
        def set_opacity(change):
            l.opacity = change['new']

        opacity_slider.observe(set_opacity, names='value')
        slider_control = WidgetControl(widget=opacity_slider, position='bottomleft')
        inMap.map.add_control(slider_control)
    return
        
def addS2Tiles(inMap):
    with open('./Shapefiles/Europe.geojson') as f:
        data = json.load(f)
    for feature in data['features']:
        feature['properties']['style'] = {
            'color': 'grey',
            'weight': 1,
            'fillColor': None,
            'fillOpacity': 0.1    }

    s2_tiles_layer = GeoJSON(data=data,name='S2_tiles')
    inMap.map.add_layer(s2_tiles_layer)
    return

def addTimeseries(inMap,path,bands,new_plot):
        px_series = xr.open_dataset(path)
        date_start = px_series.t.min().values
        date_end = px_series.t.max().values
        color = ['blue','red','green','yellow']

        for i,b in enumerate(bands):
            x_data = px_series.t.values
            y_data = px_series.to_array().loc[dict(variable=b)][:,0,0].values
            x_data = x_data[~np.isnan(y_data)]
            y_data = y_data[~np.isnan(y_data)]
            x_data = x_data[y_data!=0]
            y_data = y_data[y_data!=0]
            axes_options = {'x': {'label':'Time', 'side':'bottom', 'num_ticks':8, 'tick_format':'%b %y'}, 'y': {'orientation':'vertical', 'side':'left', 'num_ticks':10}}
            if i==0:
                title = ''
                for x in bands:
                    title += (x + ' ')
                title += ' timeseries'
                if new_plot:
                    inMap.figure = bqplt.figure(title=title,layout={'max_height': '250px', 'width': '600px'})
                else:
                    if inMap.figure is not None:
                        pass
                    else:
                        inMap.figure = bqplt.figure(title=title,layout={'max_height': '250px', 'width': '600px'})
                        

            scatt = bqplt.scatter(x_data, y_data, labels=[b], display_legend=True, colors=[color[i]], default_size=30, axes_options=axes_options)
        
        widget_control = WidgetControl(widget=inMap.figure, position='bottomright')
        if inMap.figure_widget is not None:
            inMap.map.remove_control(inMap.figure_widget)
        inMap.figure_widget = widget_control
        inMap.map.add_control(inMap.figure_widget)
        return
    
def tone_mapping(B04,B03,B02):
    red = B04.values
    green = B03.values
    blue = B02.values
    red = (red+1)/1733*255
    green = (green+1)/1630*255
    blue = (blue+1)/1347*255
    red = np.clip(red,0,255).astype(np.uint8)
    green = np.clip(green,0,255).astype(np.uint8)
    blue = np.clip(blue,0,255).astype(np.uint8)
    brg = np.zeros((red.shape[0],red.shape[1],3),dtype=np.uint8)
    brg[:,:,0] = red
    brg[:,:,1] = green
    brg[:,:,2] = blue
    return brg