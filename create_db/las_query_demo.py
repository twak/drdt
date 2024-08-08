import psycopg2
from shapely.geometry import LineString
from shapely import wkb
import urllib.request
import api.utils as utils

# coordinates of the rectangle. epsg:27700 You can explore these by using QGIS, or https://digimap.edina.ac.uk/roam/map/os and clicking
nw = (601158.9, 261757.9) # north west
se = (601205.6, 261660.2) # south east

if False: ##### demo 1 - finding LAS files in that rectangle
    # open postgres connection to the server (so needs vpn/be on cambridge network)
    curs = utils.ro_create_postgres_connection()

    # SQL query for some coordinates
    curs.execute(
        f"""
        SELECT  type, name, nas
        FROM las_chunks
        WHERE ST_Intersects
         ( geom
         , ST_MakeEnvelope ( {nw[0]} -- query box
                           , {se[1]}
                           , {se[0]}
                           , {nw[1]}
                           , 27700 -- projection epsg-code (gb national grid)
                           )::geometry('POLYGON') 
         )
        """)

    print ("las chunks I found:")
    for x in curs.fetchall():
        # the type always point clouds (for now, maybe meshes later?)
        print (f" type: {x[0]} name: {x[1]}")
        # this is a linux file path, but guess you can mount the NAS on windows, add a drive letter at the start, and it'll work...?
        print (f" location on nas: {x[2]}\n ")

else: ##### demo 2 - download a transperent PNG of the same area from geoserver

    w, h = 600, 600 # width and height of texture to download (adjust to the size of the area you're downloading).

    url = (f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3Ageotiffs&exceptions=application%2Fvnd.ogc.se_inimage&"
           f"SRS=EPSG%3A27700&WIDTH={w}&HEIGHT={h}&BBOX={nw[0]}%2C{se[1]}%2C{se[0]}%2C{nw[1]}")


    # download the url (you can just put it into your browser address bar)
    urllib.request.urlretrieve(url, "test.png")

