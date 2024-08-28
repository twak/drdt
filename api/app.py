from flask import Flask, request, redirect
import logging
import psycopg2
from shapely.geometry import LineString
import shapely
import urllib.request
import json
from . import utils

app = Flask(__name__)
app.debug = True

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


def envelope(vals):
    return (f"ST_MakeEnvelope({vals['w']}, {vals['s']}, {vals['e']}, {vals['n']}, 27700 )::geometry('POLYGON')")

"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/las_chunks

    for example, with the coords (epsg:27700)
    
    /v0/find-las?w=601158.9&n=261757.9&e=601205.6&s=261660.2

"""
@app.route("/v0/find-las")
def find_las():

    vals = get_nsew()

    if isinstance(vals, str):
        return vals, 500

    with utils.Postgres() as pg:

        pg.cur.execute(
            f"""
                SELECT  type, name, nas
                FROM las_chunks
                WHERE ST_Intersects
                ( geom, {envelope(vals)} )
                """)

        print("las chunks I found:")
        out = []
        for x in pg.cur.fetchall():
            # the type always point clouds (for now, maybe meshes later?)
            print(f" type: {x[0]} name: {x[1]}")
            out.append(x[1])

        return json.dumps(out)

    return "failed to connect to database", 500

"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/mesh_chunks

    for example, with the coords (epsg:27700)

    /v0/find-mesh?w=598227.56&n=262624.51&e=598296.11&s=262672.38

    returns a list of pairs - the first of which is the folder_name, the second is semi-colon delimetered list of files in the folder which make up the mesh:

    [["w_598260.0_262620.0", 598260.0, 262620.0, "w_598260.0_262620.0_pavement.jpg;w_598260.0_262620.0_mesh.fbx"], ["w_598270.0_262620.0", 598270.0, 262620.0, "w_598270.0_262620.0_mesh.fbx;w_598270.0_262620.0_pavement.jpg"], ...]
    
    In this output, the first mesh is made up of the files:
    
    /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_mesh.fbx
    /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_pavement.jpg
    
    with offset 598260.0, 262620.0
"""

@app.route("/v0/find-mesh")
def find_mesh():

    vals = get_nsew()

    if isinstance(vals, str):
        return vals, 500

    with utils.Postgres() as pg:

        pg.cur.execute(
            f"""
                SELECT  name, files, ST_AsText(origin)
                FROM A14_mesh_chunks
                WHERE ST_Intersects
                ( geom, {envelope(vals)} )
                """)

        print("las chunks I found:")
        out = []
        for x in pg.cur.fetchall():
            # the type always point clouds (for now, maybe meshes later?)
            pt = shapely.from_wkt(x[2])
            print(f" name: {x[0]} files: {x[1]}")
            out.append((x[0], pt.x, pt.y, x[1]))

        return json.dumps(out)

    return "failed to connect to database", 500

"""
    returns a section of the orthomosaic at resolution width x height for given 27700 area
     
    /v0/pavement?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
"""

@app.route("/v0/pavement")
def find_pavement():

    vals = get_nsew(opt={"scale":1})
    if isinstance(vals, str):
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float (vals['n']) - float(vals['s'])) * float(vals['scale'])
    width  = (float(vals['e']) - float(vals['w'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_pavement_orthomosaics&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['w']}%2C{vals['s']}%2C{vals['e']}%2C{vals['n']}", code=302)


"""
    returns a section of the orthomosaic at resolution width x height for given 27700 area

    /v0/aerial?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
"""

@app.route("/v0/aerial")
def find_aerial():

    vals = get_nsew(opt={"scale":10})
    if isinstance(vals, str):
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float(vals['n']) - float(vals['s'])) * float(vals['scale'])
    width = (float(vals['e']) - float(vals['w'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_aerial&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['w']}%2C{vals['s']}%2C{vals['e']}%2C{vals['n']}", code=302)


# @app.route("/v0/create_scenario")
# def create_scenario():
#     try:
#         name = request.args['name']
#
#         scenarios = dbz.get_row("scenarios", name)
#         if name in scenarios:
#             return f"scenario {name} already exists"
#
#         dbz.insert_row("scenarios", {"name": name, "created": "now()"})
#
#         for dataset in ["A14"]:
#             for table in ["las_chunks", "mesh_chunks"]:
#                 dbz.create_table_from(f"{name}_{dataset}_{table}", f"{dataset}_{table}" )
#
#         return "success"
#     except:
#         return "error!"