import sys

import api.utils as utils
from api.utils import Postgres
from  shapely import wkb
import shutil, os
import urllib.request
import uuid

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
            WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 1)
            """)


        for x in pg.cur:


            print (f" type: {x[0]} name: {x[1]}")
            # this is a linux file path, but guess you can mount the NAS on windows, add a drive letter at the start, and it'll work...?
            print (f" location on nas:  { x[2]} and origin: { wkb.loads( x[3] )}\n ")

            c2 = pg.con.cursor()
            origin = wkb.loads( x[3] )

            # if no origin in mesh_chunks database, then.

            workdir = os.path.join ("/home/twak/Downloads", f"{origin.x}_{origin.y}" )
            if os.path.exists(workdir):
                continue # already done this
            os.makedirs(workdir, exist_ok=False)

            for i in range (3):
                os.makedirs(workdir, f"stage{i}", exist_ok=True)

            c2.execute (
                f"""
                SELECT type,name
                FROM public.las_chunks
                WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint({origin.x +5}, {origin.y+5}), 27700 ) , 10)
                """
            )

            # download nearby las files
            for y in c2:
                print (f" >>>> type: {y[0]} name: {y[1]}")
                shutil.copy (os.path.join (utils.nas_mount+utils.las_route, y[1]), os.path.join(workdir, "stage1", y[1]) )

            # download textures
            urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={origin.x}&s={origin.y}&e={origin.x+10}&n={origin.y+10}&scale=100", os.path.join(workdir, "stage2", "pavement.png"))
            urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={origin.x}&s={origin.y}&e={origin.x + 10}&n={origin.y + 10}&scale=20", os.path.join(workdir, "stage2", "aerial.png"))

            # run pdal

            # do meshing. copy to
            shutil.copy()



if __name__ == "__main__":
    go()