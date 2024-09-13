import sys

import api.utils as utils
from api.utils import Postgres
from shapely import wkb, Polygon
import shutil, os
import urllib.request
import uuid
import subprocess
from pathlib import Path
import shapely
from shapely.geometry import Point
import laspy

"""
This processes the chunked las files from gpr (chunk_gpr.py - about 20 files with pts in planes over each square) into 3D cubes of las files at the origin. 
The offset in the las is zero, and bng offset is stored in db.
"""

def run_pdal_scripts_import(workdir, las_files, x, y, name):

    # classes = [0,2,3,4,5,6,7,8,9,11,12] # exclude cars and other

    with open(os.path.join ( workdir, f"go_{name}.json"), "w") as fp:

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')


        fp.write(f'''
                {{
                    "type": "filters.merge"
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
                    "type": "writers.las",
                    "filename": "{utils.nas_mount_w}{utils.gpr_route}/{name}.las"
                }}
                ]
                ''')

        # this requires pdal in the current path (use conda!)
    print("merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline go_{name}.json', shell=True, executable='/bin/bash')

import create_db.chunk_gpr as chunk_gpr

def merge_and_filter_pts(workdir,  x,y, name):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(workdir ) ) )
    run_pdal_scripts_import(workdir, las_files, x,y, name )
    return os.path.exists(os.path.join( utils.nas_mount_w + utils.gpr_route, f"{name}.las"))

gprs = f"{utils.nas_mount_w}{utils.gpr_route}"
chunk_size = 10 # meters
scratch = "/home/twak/Downloads/foo"
table_name = "a14_gpr_chunks"

defect_chunks = f"{utils.nas_mount_w}{utils.gpr_defect_route}"

def setup():

    os.makedirs(gprs, exist_ok=True)
    with Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f'DROP TABLE IF EXISTS {table_name}')
        pg.cur.execute(
            f'CREATE TABLE {table_name} (geom geometry, name text, nas text, origin geometry(Point, {utils.sevenseven}), existence tsmultirange)' )

        pg.con.commit()

def chunk0():
    with Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute( f"""
            SELECT  type, name, nas, origin
            FROM public.{chunk_gpr.table_name}
--             WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 1)  debug!
            """ )

        for x in pg.cur:

            print ( f" type: {x[0]} name: {x[1]}" )
            print ( f" location on nas:  { x[2]} and origin: { wkb.loads( x[3] )}\n " )

            c2 = pg.con.cursor()
            origin = wkb.loads( x[3] )

            # workdir = os.path.join (utils.nas_mount+utils.mesh_route, f"{origin.x}_{origin.y}" )
            chunk_name = f"w_{origin.x}_{origin.y}" # _w_indows friendly filename
            chunk_file = f"{chunk_name}.las"

            if os.path.exists(f"{gprs}/{chunk_file}"):
                print(f"output {chunk_file} already exists, skipping")
                continue # guess we've already done this

            workdir = os.path.join(scratch, chunk_name)
            os.makedirs(workdir, exist_ok=True)

            ls = Polygon([
                [origin.x, origin.y],
                [origin.x, origin.y + chunk_size],
                [origin.x + chunk_size, origin.y + chunk_size],
                [origin.x + chunk_size, origin.y]
            ])

            c2.execute (
                f"""
                SELECT type,name, geom
                FROM public.{chunk_gpr.table_name}
                WHERE ST_DWithin(geom, ST_SetSRID( '{ls.wkb_hex}'::geometry, 27700 ) , 2) 
                """
            )

            # download all nearby las files
            for y in c2:
                print (f" >>>> downloading {y[1]}...")
                dp = os.path.join ( workdir, y[1] )
                if not os.path.exists(dp):
                    shutil.copy (os.path.join ( f"{utils.nas_mount}{utils.gpr_route}_tmp", y[1]), dp )

            # # run pdal, merge and filter point clouds
            if merge_and_filter_pts (workdir, origin.x, origin.y, chunk_name):
            #
            #     shutil.copyfile( os.path.join(workdir, chunk_file), os.path.join(lasos, chunk_file ) )
            #

            #
                print("inserting into db...")
                c2.execute(
                    f'INSERT INTO {table_name}(geom, name, nas, origin, existence) '
                    'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s), %(existence)s )',
                    {'geom': ls.wkb_hex, 'srid': 27700, 'name': chunk_file, 'nas': f"{utils.laso_route}/{chunk_file}", 'origin': origin.wkb_hex, 'existence': utils.before_time_range })
            #
                pg.con.commit()
            else:
                print(f"something went wrong merging point clouds for {chunk_name}")
            #
            shutil.rmtree(workdir)


def run_pdal_scripts_defects( workdir, x, y, area ):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(workdir ) ) )

    klass = "defect_gpr"

    with open(os.path.join ( workdir, f"go_{klass}.json"), "w") as fp:

        print (f"generating {klass}")

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        fp.write(f'''
                {{
                    "type": "filters.merge"
                }},
                {{
                    "type":"filters.crop",
                    "polygon":"{area}"
                }},
                {{
                    "type":"filters.transformation",
                    "matrix":"1 0 0 -{x} 0 1 0 -{y} 0 0 1 {-50} 0 0 0 1"
                }},
                {{
                    "type": "writers.las",
                    "filename": "{workdir}/{klass}.las"
                }}
                ]
                ''')

    # this requires pdal in the current path (use conda!)
    print("merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline {workdir}/go_{klass}.json', shell=True, executable='/bin/bash')

def defects():

    os.makedirs(defect_chunks, exist_ok=True)

    count = 0

    with Postgres(pass_file="pwd_rw.json") as pg:
        pg.cur.execute(
            f"""
                    SELECT geom, id, type, layer
                    FROM public.a14_defects_cam
--                     WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 10)
                    """)

        for x in pg.cur:

            print (f"defect# >> {count} / {pg.cur.rowcount}")
            count += 1

            # try:
            geom = wkb.loads(x[0])
            id = x[1]
            type = x[2]
            layer = x[3]

            bounds = shapely.bounds(geom)
            buffer = geom.buffer(0.2, cap_style='flat')
            buffer_bounds = shapely.bounds(buffer)
            origin = buffer_bounds[:2]

            print(f" type: {type} name: {layer}")

            c2 = pg.con.cursor()

            pothole_name = f"w_{id}"  # _w_indows friendly filename
            workdir = os.path.join(scratch, pothole_name)

            if os.path.exists(f"{defect_chunks}/{pothole_name}"):
                print("output already exists, skipping")
                continue  # guess we've already done this

            os.makedirs(workdir, exist_ok=True)

            c2.execute(
                f"""
                SELECT nas,name, geom, origin
                FROM public.{table_name}
                WHERE ST_Intersects(geom, ST_SetSRID( '{buffer.wkb_hex}'::geometry, 27700 ) )
                """
            )

            if c2.rowcount == 0:
                print(f"no chunks found for {id}")
                continue

            for y in c2:
                print(f" >>>> downloading {y[1]}...")
                dest = os.path.join(workdir, y[1])
                if not os.path.exists(dest):
                    shutil.copy(os.path.join(utils.nas_mount + utils.gpr_route, y[1]), dest)
                    las_origin = wkb.loads(y[3])
                    utils.offset_las(dest, las_origin.x, las_origin.y)

            # run pdal, merge and filter point clouds
            run_pdal_scripts_defects(workdir, origin[0], origin[1], buffer.wkt)

            work_las = os.path.join(workdir, f"defect_gpr.las" )
            if os.path.exists(work_las):
                with laspy.open(work_las) as fh:
                    print(f'{id} - num_points:', fh.header.point_count)
                    if fh.header.point_count > 100:  # many potholes are in a different lane to the gpr tracks...

                        out_las = os.path.join(defect_chunks, f"{pothole_name}.las")
                        shutil.copyfile(work_las, out_las)

                        print("updating db...")
                        c2.execute(
                            f"UPDATE public.a14_defects_cam SET "
                            f"gpr_nas    = '{utils.gpr_defect_route}/{pothole_name}.las' "
                            f"WHERE id = {id};"
                        )

                        pg.con.commit()

                    else:
                        print ( f"skipping {id} as not enough las data found" )

            shutil.rmtree(workdir)

            # except Exception as e:
            #     print(f"error: {e}")
            #     continue

if __name__ == "__main__":
    # setup() # create table and dirs
    # chunk0() # chunks to origin
    defects() # cut out defect las clouds