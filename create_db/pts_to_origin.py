import sys

import api.utils as utils
from api.utils import Postgres
from shapely import wkb, Polygon
import shutil, os
import urllib.request
import uuid
import subprocess
from pathlib import Path

"""
This processes the chunked las files into cubes of las files at the origin. The offset is stored in the laso table.
"""

def run_pdal_scripts(workdir, las_files, x, y, name):

    classes = [0,2,3,4,5,6,7,8,9,11,12] # exclude cars and other

    with open(os.path.join ( workdir, f"go_{name}.json"), "w") as fp:

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        clst = []
        for c in classes:
            clst .append( f"Classification[{c}:{c}]" )
        clst = ", ".join(clst)

        fp.write(f'''
                {{
                    "type": "filters.merge"
                }},
                {{
                    "type":"filters.range",
                    "limits":"{clst}"
                }},
                {{
                    "type":"filters.transformation",
                    "matrix":"1 0 0 -{x} 0 1 0 -{y} 0 0 1 {-50} 0 0 0 1"
                }},
                {{
                    "type":"filters.crop",
                    "bounds":"([0,10],[0,10])"
                }},
                {{
                    "type": "writers.e57",
                    "filename": "{name}.e57"
                }}
                ]
                ''')

        # this requires pdal in the current path (use conda!)
    print("merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline go_{name}.json', shell=True, executable='/bin/bash')


def merge_and_filter_pts(workdir,  x,y, name):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(workdir ) ) )
    run_pdal_scripts(workdir, las_files, x,y, name )
    return os.path.exists(os.path.join(workdir, f"{name}.e57"))

def go():

    lasos = f"{utils.nas_mount_w}{utils.laso_route}"
    os.makedirs(lasos, exist_ok=True)
    chunk_size = 10 # meters
    scratch = "/home/twak/Downloads/foo"
    table_name = "A14_laso_chunks"

    with Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f'DROP TABLE IF EXISTS {table_name}')
        pg.cur.execute(
            f'CREATE TABLE {table_name} (geom geometry(Polygon, {utils.sevenseven}), name text, nas text, origin geometry(Point, {utils.sevenseven}), existence tsmultirange)')
        pg.con.commit()

        pg.cur.execute(
            f"""
            SELECT  type, name, nas, origin
            FROM public."A14_las_chunks"
            WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 1)
            """)

        for x in pg.cur:

            print (f" type: {x[0]} name: {x[1]}")
            print (f" location on nas:  { x[2]} and origin: { wkb.loads( x[3] )}\n ")

            c2 = pg.con.cursor()
            origin = wkb.loads( x[3] )

            # workdir = os.path.join (utils.nas_mount+utils.mesh_route, f"{origin.x}_{origin.y}" )
            chunk_name = f"w_{origin.x}_{origin.y}" # _w_indows friendly filename
            chunk_file = f"{chunk_name}.e57"

            if os.path.exists(f"{lasos}/{chunk_file}"):
                print("output already exists, skipping")
                continue # guess we've already done this

            workdir = os.path.join(scratch, chunk_name)
            os.makedirs(workdir, exist_ok=True)


            c2.execute (
                f"""
                SELECT type,name, geom
                FROM public."A14_las_chunks"
--                 WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint({origin.x + chunk_size/2}, {origin.y + chunk_size/2}), 27700 ) , 10) # debug
                """
            )

            # download all nearby las files
            for y in c2:
                print (f" >>>> downloading {y[1]}...")
                dp = os.path.join ( workdir, y[1])
                if not os.path.exists(dp):
                    shutil.copy (os.path.join ( utils.nas_mount+utils.las_route, y[1]), dp )

            # run pdal, merge and filter point clouds
            if merge_and_filter_pts (workdir, origin.x, origin.y, chunk_name):

                shutil.copyfile( os.path.join(workdir, chunk_file), os.path.join(lasos, chunk_file ) )

                ls = Polygon([
                    [origin.x, origin.y],
                    [origin.x, origin.y + chunk_size],
                    [origin.x + chunk_size, origin.y + chunk_size],
                    [origin.x + chunk_size, origin.y]
                ])

                print("inserting into db...")
                c2.execute(
                    f'INSERT INTO {table_name}(geom, name, nas, origin, existence) '
                    'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s), %(existence)s )',
                    {'geom': ls.wkb_hex, 'srid': 27700, 'name': chunk_file, 'nas': f"{utils.laso_route}/{chunk_file}", 'origin': origin.wkb_hex, 'existence': utils.before_time_range })

                pg.con.commit()

            shutil.rmtree(workdir)



if __name__ == "__main__":
    go()