import sys

import api.utils as utils
from api.utils import Postgres
from  shapely import wkb
import shutil, os
import urllib.request
import uuid
import subprocess

"""
for each las chunk we create a mesh:
 - download all adjacent las files
 - download texture for the central las chunk
 - use pdal to filter & merge point clouds
 - use blender to create a mesh, crop, set uvs, and project texture
"""


def run_pdal_scripts(workdir, las_files, classes, x, y):

    out_folder = "stage2"

    for klass in classes.keys():
        with open(os.path.join ( workdir, out_folder, f"go_{klass}.json"), "w") as fp:

            print (f"generating {klass}")

            fp.write("[\n")
            for f in las_files:
                fp.write(  f'"stage1/{f}", \n')

            clst = []
            for c in classes.get(klass):
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
                        "type": "writers.ply",
                        "filename": "{out_folder}/{klass}.ply"
                    }}
                    ]
                    ''')

        # this requires pdal in the current path (use conda!)
        subprocess.run(f'cd {workdir} && pdal pipeline {out_folder}/go_{klass}.json', shell=True, executable='/bin/bash')


def merge_and_filter_pts(workdir="/home/twak/Downloads/d6098df3-bc8e-4696-950e-30cfb4066ef5/",  x=598555.51,y=262383.29):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(os.path.join(workdir, "stage1" ) ) ) )
    classes = {}
    classes["vegetation"] = [3, 4, 5]
    classes["road"] = [2, 7, 8, 9, 11]
    run_pdal_scripts(workdir, las_files, classes, x,y )

def run_blender(input_dir, output_dir):
    # subprocess.run(f'', shell=True, executable='/bin/bash')
    pass

def go():

    with Postgres(pass_file="pwd_rw.json") as pg:

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

            # workdir = os.path.join (utils.nas_mount+utils.mesh_route, f"{origin.x}_{origin.y}" )
            workdir = os.path.join ("/home/twak/Downloads", f"{origin.x}_{origin.y}" )

            # if os.path.exists(workdir):
            #     continue # already done this
            os.makedirs(workdir, exist_ok=True)

            for i in range (1,4):
                os.makedirs( os.path.join ( workdir, f"stage{i}"), exist_ok=True)

            c2.execute (
                f"""
                SELECT type,name
                FROM public.las_chunks
                WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint({origin.x +5}, {origin.y+5}), 27700 ) , 10)
                """
            )

            # download nearby las files
            for y in c2:
                print (f" >>>> downloading {y[1]}...")
                dest = os.path.join(workdir, "stage1", y[1])
                if not os.path.exists(dest):
                    shutil.copy (os.path.join (utils.nas_mount+utils.las_route, y[1]), dest )

            # run pdal, merge and filter point clouds
            merge_and_filter_pts (workdir, origin.x, origin.y)

            # download textures
            urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={origin.x}&s={origin.y}&e={origin.x+10}&n={origin.y+10}&scale=100", os.path.join(workdir, "stage2", "pavement.png"))
            urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={origin.x}&s={origin.y}&e={origin.x + 10}&n={origin.y + 10}&scale=20", os.path.join(workdir, "stage2", "aerial.png"))

            # create fbx files
            run_blender(os.path.join(workdir, "stage2"), os.path.join(workdir) )

            # save to mesh table
            # c2.execute(
            #     f'INSERT INTO mesh_chunks(geom, type, name, nas, origin)'
            #     'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(type)s, %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s) )',
            #     {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'mesh', 'name': file_name, 'nas': nas_file, 'origin': origin.wkb_hex})




if __name__ == "__main__":
    go()