from flask import Flask, request, redirect
import logging
import psycopg2
from shapely.geometry import LineString
from shapely import wkb
import urllib.request
import json

import api.utils as utils

# import requests

app = Flask(__name__)
app.debug = True

# coordinates of the rectangle. You can explore these by using QGIS, or https://digimap.edina.ac.uk/roam/map/os and clicking


curs = utils.create_postgres_connection()


def get_nsew(other=[],opt={}):
    vals = {}
    for x in ['n', 'w', 's', 'e']+other:
        if not x in request.args:
            return f"missing parameters {x}"
        vals[x]= request.args[x]

    for x in opt.keys():
        if x in request.args:
            vals[x] = request.args[x]
        else:
            vals[x] = opt[x]

    return vals

@app.route('/')
def index():
    logging.warning("See this message in Flask Debug Toolbar!")
    return "<html><body>i am digital twin</body></html>"


"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/las_chunks

    for example, with the coords (epsg:27700)
     nw = (601158.9, 261757.9) # north west
     se = (601205.6, 261660.2) # south east
     
     we call:
        
    /v0/find-las?n=601158.9&w=261757.9&s=601205.6&e=261660.2
"""
@app.route("/v0/find-las")
def find_las():

    vals = get_nsew()

    curs.execute(
        f"""
            SELECT  type, name, nas
            FROM las_chunks
            WHERE ST_Intersects
             ( geom
             , ST_MakeEnvelope ( {vals['n']} -- query box
                               , {vals['e']}
                               , {vals['s']}
                               , {vals['w']}
                               , 27700 -- projection epsg-code (gb national grid)
                               )::geometry('POLYGON') 
             )
            """)

    print("las chunks I found:")
    out = []
    for x in curs.fetchall():
        # the type always point clouds (for now, maybe meshes later?)
        print(f" type: {x[0]} name: {x[1]}")
        out.append(x[1])

    return json.dumps(out)

"""
    returns a section of the orthomosaic at resolution width x height for given 27700 area
     
    /v0/pavement?n=601158.9&w=261757.9&s=601205.6&e=261660.2&scale=10
"""

@app.route("/v0/pavement")
def find_pavement():

    vals = get_nsew(opt={"scale":1})
    if isinstance(vals, str):
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float (vals['w']) - float(vals['e'])) * float(vals['scale'])
    width  = (float(vals['s']) - float(vals['n'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_pavement_orthomosaics&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['n']}%2C{vals['e']}%2C{vals['s']}%2C{vals['w']}", code=302)


"""
    returns a section of the orthomosaic at resolution width x height for given 27700 area

    /v0/aerial?n=601158.9&w=261757.9&s=601205.6&e=261660.2&scale=10
"""

@app.route("/v0/aerial")
def find_aerial():

    vals = get_nsew(opt={"scale":10})
    if isinstance(vals, str):
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float (vals['w']) - float(vals['e'])) * float(vals['scale'])
    width  = (float(vals['s']) - float(vals['n'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_aerial&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['n']}%2C{vals['e']}%2C{vals['s']}%2C{vals['w']}", code=302)
