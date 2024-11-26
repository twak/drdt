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
 restores the mesh table from the files + las table...
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
        print("merging and filtering point clouds...")
        subprocess.run(f'cd {workdir} && pdal pipeline {out_folder}/go_{klass}.json', shell=True, executable='/bin/bash')


def merge_and_filter_pts(workdir=f"{utils.scratch}/d6098df3-bc8e-4696-950e-30cfb4066ef5/",  x=598555.51,y=262383.29):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(os.path.join(workdir, "stage1" ) ) ) )
    classes = {}
    classes["vegetation"] = [3, 4, 5]
    classes["road"] = [2, 7, 8, 9, 11]
    run_pdal_scripts(workdir, las_files, classes, x,y )

def run_blender( workdir ):

    # call blender to run the meshing script from its directory
    workdir = Path(workdir)
    print("running blender...")

    out = subprocess.run(f'cd {Path(__file__).parent.parent.joinpath("blender")} &&'
                   f'{utils.blender_binary} -b pts_to_mesh.blend --python blender_pts_to_mesh.py -- '
                   f'--cycles-device OPTIX --root="{workdir.parent}" --name="{workdir.name}"',
                   shell=True, executable='/bin/bash')

    return out.returncode

def go():

    mesh_chunks = f"{utils.nas_mount}{utils.mesh_route}"
    table_name = "a14_mesh_chunks"
    chunk_size = 10
    scratch = f"{utils.scratch}/foo"

    with Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f'DROP TABLE IF EXISTS {table_name}')
        pg.cur.execute(
            f'CREATE TABLE {table_name} (geom geometry(Polygon, {utils.sevenseven}), name text, nas text, files text, origin geometry(Point, {utils.sevenseven}), existence tsmultirange)')
        pg.con.commit()

        pg.cur.execute(
            f"""
            SELECT  type, name, nas, origin
            FROM public.a14_las_chunks
--             WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 1)
            """)

        for x in pg.cur:

            print (f" type: {x[0]} name: {x[1]}")
            # this is a linux file path, but guess you can mount the NAS on windows, add a drive letter at the start, and it'll work...?
            print (f" location on nas:  { x[2]} and origin: { wkb.loads( x[3] )}\n ")

            c2 = pg.con.cursor()
            origin = wkb.loads( x[3] )

            # if no origin in mesh_chunks database, then.

            # workdir = os.path.join (utils.nas_mount+utils.mesh_route, f"{origin.x}_{origin.y}" )
            chunk_name = f"w_{origin.x}_{origin.y}" # _w_indows friendly filename
            # workdir = os.path.join (scratch, chunk_name )

            # if os.path.exists(f"{mesh_chunks}/{chunk_name}"):
            #     print("output already exists, skipping")
            #     continue # guess we've already done this
            #
            # os.makedirs(workdir, exist_ok=True)
            #
            # for i in range (1,4):
            #     os.makedirs( os.path.join ( workdir, f"stage{i}"), exist_ok=True)
            #
            # c2.execute (
            #     f"""
            #     SELECT type,name
            #     FROM public.a14_las_chunks
            #     WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint({origin.x + chunk_size/2}, {origin.y + chunk_size/2}), 27700 ) , 10)
            #     """
            # )
            #
            # # download nearby las files
            # for y in c2:
            #     print (f" >>>> downloading {y[1]}...")
            #     dest = os.path.join(workdir, "stage1", y[1])
            #     if not os.path.exists(dest):
            #         shutil.copy (os.path.join (utils.nas_mount+utils.las_route, y[1]), dest )
            #
            # # run pdal, merge and filter point clouds
            # merge_and_filter_pts (workdir, origin.x, origin.y)
            #
            # # download textures
            # urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={origin.x}&s={origin.y}&e={origin.x+10}&n={origin.y+10}&scale=100", os.path.join(workdir, "stage2", "pavement.png"))
            # urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={origin.x}&s={origin.y}&e={origin.x + 10}&n={origin.y + 10}&scale=20", os.path.join(workdir, "stage2", "aerial.png"))
            #
            # # create fbx files
            file_str = []
            # if run_blender( workdir ) == 0:
            #
            #     #save to mesh table
            to = os.path.join ( mesh_chunks, chunk_name)
            #
            #     os.makedirs(to, exist_ok=True)
            for f in os.listdir(to):
                # print (f"copying mesh file {f} to nas...")
                # shutil.copyfile( os.path.join(workdir, "stage3", f), os.path.join(to, f) )
                file_str.append(f)

            file_str = ";".join(file_str)

            # extent of the mesh in 27700
            ls = Polygon([
                [origin.x, origin.y],
                [origin.x, origin.y + chunk_size],
                [origin.x + chunk_size, origin.y + chunk_size],
                [origin.x + chunk_size, origin.y]
            ])

            print("inserting into db...")
            c2.execute(
                f'INSERT INTO public.{table_name}(geom, name, nas, files, origin, existence) '
                'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(name)s, %(nas)s, %(files)s, ST_SetSRID(%(origin)s::geometry, %(srid)s ), \'{["2021-01-01 00:00:00",)}\' )',
                {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': chunk_name, 'nas': f"{utils.mesh_route}/{chunk_name}", 'files':file_str, 'origin': origin.wkb_hex})

            pg.con.commit()

            # shutil.rmtree(workdir)



if __name__ == "__main__":
    go()