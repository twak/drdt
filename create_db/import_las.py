import math
import os
import sys
import laspy
import numpy as np
from pyhull.convex_hull import ConvexHull

import psycopg2
from shapely.geometry import Polygon, Point

from api.utils import create_postgres_connection
import api.utils as utils
from api.utils import Postgres

import subprocess

"""
For all las files, this breaks them up into chunks and adds them and their bounds to a db table.

chunk_las.py was combined into this 27.11.24.

"""

# las_dir = "/06. Data/4. Roads/Cambridge University - National Highways Data/DRF Dataset FULL/01-PointClouds/PointCloud-A14EBWBJ47AWoolpittoHaugleyBridge/labelled"
las_dir = "/06. Data/4. Roads/Cambridge University - National Highways Data/DRF Dataset FULL/01-PointClouds/PointCloud-A11EBWBSpoonerstoBracklandRailwayA11EBWBBrecklandRailwaytoTuttles/labelled"
road = "A11"
work_dir = f"{utils.scratch}/pdal_jsons"
# this is the database table we save to. We can merge it into main table when we've checked it's right.
table_name="las_chunks_tmp"
las_write_dir = f"/08. Researchers/tom/{road}/las_chunks"

def setup_db():
    with Postgres(pass_file="pwd_rw.json") as pg2:
        print("removing old table...")
        pg2.cur.execute(f'DROP TABLE IF EXISTS {table_name}')
        print("...creating new table...")
        pg2.cur.execute(f'CREATE TABLE {table_name} (geom geometry, type text, name text, nas text, origin geometry(Point, {utils.sevenseven}), existence tsmultirange )')
        print("...")

    print("done")


def convex_hull(lasdata, file_name):
    try:
        hull = ConvexHull(lasdata)
    except Exception:
        print(f"skipping {file_name} on qhull issue")
        return None

    if len(hull.vertices) == 0:
        print(f"skipping {file_name} on qhull zero length output")
        return None

    m = {}
    for [x, y] in hull.vertices:
        m[x] = y

    start = hull.vertices[0][0]
    current = None

    loop = []

    while current != start:
        if current is None:
            current = start
        current = m[current]

        loop.append(current)

    return list(map(lambda x: lasdata[x], loop + [loop[0]]))  # map index to coords; last point is first


def add_chunks_db(chunk_root, use_hull = False):

    print("starting...")
    for file_name in os.listdir(f"{utils.nas_mount}{las_write_dir}"): # ['out_982.las']:
        print(f"file {file_name}")
        if file_name.endswith(".las"):
            with laspy.open( os.path.join ( f"{utils.nas_mount}{las_write_dir}", file_name) ) as fh:
                print(f'{file_name} - num_points:', fh.header.point_count)
                # if fh.header.point_count < 3:
                #     continue

                lasdata = fh.read().xyz[:,:2] # 2d hull

                mm = utils.min_max(lasdata)

                if use_hull:
                    boundary = convex_hull (lasdata, file_name)
                else:
                    boundary = [
                                [mm[0], mm[1]],
                                [mm[0], mm[3]],
                                [mm[2], mm[3]],
                                [mm[2], mm[1]] ]

                if boundary is None: # not enough points for bb
                    continue

                ls = Polygon(boundary)
                origin = Point(utils.round_down( mm[0] ), utils.round_down( mm[1] ) )

                nas_file = f"{las_write_dir}/{file_name}"

                # https://gis.stackexchange.com/questions/108533/insert-a-point-into-postgis-using-python

                with Postgres(pass_file="pwd_rw.json") as pg2:
                    pg2.cur.execute(
                        f'INSERT INTO {table_name}(geom, type, name, nas, origin, existence)'
                        'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(type)s, %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s), %(existence)s )',
                        {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': file_name, 'nas': nas_file, 'origin': origin.wkb_hex, 'existence': utils.before_time_range})

    # create an index to accelerate queries
    with Postgres(pass_file="pwd_rw.json") as pg2:
        pg2.cur.execute (
            f"""
            CREATE INDEX IF NOT EXISTS chunk_geom_idx
              ON {table_name}
              USING GIST (geom);
            """
        )


def chunk_file(prefix):
    print(f"chunking {prefix}")

    with open(os.path.join(f"{work_dir}", prefix + ".json"), "w") as fp:
        fp.write(f'''
    [
        "{utils.nas_mount}{las_dir}/HE-PHASE-2_{road}_{prefix} - Cloud.las",
        {{
            "type":"filters.splitter",
            "length":"10",
            "origin_x":"600000.000",
            "origin_y":"261000.000"
        }},
        {{
            "type":"writers.las",
            "filename":"{utils.nas_mount_w}{las_write_dir}/{prefix}_#.las"
        }}
    ]
    ''')

    print("merging and filtering point clouds...")
    ret = subprocess.run(f'cd "{work_dir}" && pdal pipeline "{prefix}.json"', shell=True, executable='/bin/bash')
    if ret.returncode != 0:
        print(f"something went wrong with {prefix}")
        sys.exit(1)

def chunk_big_las():
    """
    For all las files, this breaks them up into chunks.
    """
    for filename in os.listdir(f"{utils.nas_mount}{las_dir}"):
        parts = filename.split("_")
        t = parts[3].split(" ")[0]
        chunk_file(f"{parts[2]}_{t}")

    return f"{work_dir}/chunks"

if __name__ == "__main__":

    os.makedirs(f"{utils.nas_mount_w}{las_write_dir}", exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    chunk_location = chunk_big_las()
    setup_db()
    add_chunks_db(chunk_location)

