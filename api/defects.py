import flask
from flask import Flask, request, redirect
import shapely
import urllib.request
import json
from pathlib import Path
import flask_login
from . import utils
import hashlib
import uuid
import bcrypt
from flask import Response
from shapely import wkb, Polygon

def request_site():
    with utils.Postgres() as pg:

        pg.cur.execute(f"SELECT id, geom, type, ST_Area(geom ) as area FROM public.a14_defects_cam "
                       f"WHERE type='crack_longitudinal' OR type='crack_transverse'"
                       f"ORDER BY -ST_Area(geom ) "
                       f"LIMIT 1" )

        if pg.cur.rowcount == 0:
            return "[]"

        for x in pg.cur:
            print (f" {x[0]} {x[2]} {x} {wkb.loads(x[1], hex=True) } ")
            return json.dumps( [ x[0], x[2], x[3], wkb.loads(x[1], hex=True).wkt ] )

    return "[]"

def show_cracks():

    out = "<html><body><table border=1>"
    out += "<tr><th>id</th><th>type</th><th>area</th><th>orthomosaic</th></tr>"

    with utils.Postgres() as pg:

        pg.cur.execute(f"SELECT id, geom, type, ST_Area(geom ) as area, ST_Envelope(geom)  FROM public.a14_defects_cam "
                       f"WHERE type='crack_longitudinal' OR type='crack_transverse'"
                       f"ORDER BY -ST_Area(geom )" )


        for x in pg.cur:
            bounds = Polygon ( wkb.loads(x[4], hex=True) ).bounds

            res_x = bounds[2] - bounds[0]
            res_y = bounds[3] - bounds[1]
            res = 20

            url = (f"{utils.geoserver_url}/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                    f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_pavement_orthomosaics&exceptions=application%2Fvnd.ogc.se_inimage&"
                    f"SRS=EPSG%3A27700&WIDTH={int(res_x * res)}&HEIGHT={int(res_y * res)}&"
                    f"&BBOX={bounds[0]}%2C{bounds[1]}%2C{bounds[2]}%2C{bounds[3]}")

            out += f"<tr><td>{x[0]}</td><td>{x[2]}</td><td>{x[3]}</td><td><a href='{url}'>image</a></td></tr>"

    out += "</table></body></html>"

    return out