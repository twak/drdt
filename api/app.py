from flask import Flask, request
import logging
import psycopg2
from shapely.geometry import LineString
from shapely import wkb
import urllib.request
import json

app = Flask(__name__)
app.debug = True

# coordinates of the rectangle. You can explore these by using QGIS, or https://digimap.edina.ac.uk/roam/map/os and clicking

with open ("api/pwd.json") as fp:
    pwp = json.load(fp)

conn = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
curs = conn.cursor()

@app.route('/')
def index():
    logging.warning("See this message in Flask Debug Toolbar!")
    return "<html><body>boo</body></html>"

    # nw = (601158.9, 261757.9) # north west
    # se = (601205.6, 261660.2) # south east

"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/las_chunks
        
    /v0/find-las?n=601158.9&w=261757.9&s=601205.6&e=261660.2
"""
@app.route("/v0/find-las")
def find_las():

    vals = {}
    for x in ['n', 'w', 's', 'e']:
        if not x in request.args:
            return f"missing parameters {x}"
        vals[x]= request.args[x]


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