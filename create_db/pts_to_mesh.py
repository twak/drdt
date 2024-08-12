import sys

import api.utils as utils
from api.utils import Postgres
from  shapely import wkb
import shutil, tempfile, os
import urllib.request

"""
for each las chunk we create a mesh:
 - download all adjacent las files
 - download texture for the central las chunk
 - use pdal to filter & merge point clouds
 - use blender to create a mesh, crop, set uvs, and project texture
"""

def go():

    with Postgres(pass_file="newboy_pwd_rw.json") as pg:

        pg.cur.execute(
            f"""
            SELECT  type, name, nas, origin
            FROM public.las_chunks
            """)

        for x in pg.cur:

            temp_dir = tempfile.TemporaryDirectory()
            print(temp_dir)

            print (f" type: {x[0]} name: {x[1]}")
            # this is a linux file path, but guess you can mount the NAS on windows, add a drive letter at the start, and it'll work...?
            print (f" location on nas:  { x[2]} and origin: { wkb.loads( x[3] )}\n ")

            c2 = pg.con.cursor()
            origin = wkb.loads( x[3] )

            c2.execute (
                f"""
                SELECT type,name
                FROM public.las_chunks
                WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint({origin.x +5}, {origin.y+5}), 27700 ) , 10)
                """
            )

            for y in c2:
                print (f" >>>> type: {y[0]} name: {y[1]}")
                shutil.copy (os.path.join (utils.nas_mount+utils.las_route, y[1]), temp_dir.name )

            urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={origin.x}&s={origin.y}&e={origin.x+10}&n={origin.y+10}&scale=100", os.path.join(temp_dir.name, "pavement.png"))
            urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={origin.x}&s={origin.y}&e={origin.x + 10}&n={origin.y + 10}&scale=20", os.path.join(temp_dir.name, "aerial.png"))

            sys.exit(0)

if __name__ == "__main__":
    go()