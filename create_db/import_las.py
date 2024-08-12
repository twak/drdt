import math
import os

import laspy
import numpy as np
from pyhull.convex_hull import ConvexHull

import psycopg2
from shapely.geometry import Polygon, Point

from api.utils import create_postgres_connection
import api.utils as utils

"""
Given a set of las chunks (chunk_las.py), this adds them and their bounds to a postgis table.
"""

def setup_db():

    curs, con = create_postgres_connection()

    curs.execute('DROP TABLE IF EXISTS las_chunks')
    curs.execute(f'CREATE TABLE las_chunks (geom geometry, type text, name text, nas text, origin geometry(Point, {utils.sevenseven}))')
    con.commit()


def convex_hull(lasdata):
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

def min_max (lasdata):

    return (lasdata[:,0].min(), lasdata[:,1].min(), lasdata[:,0].max(), lasdata[:,1].max() )

def round_down (x):
    return math.floor(x/10)*10

def add_chunks_db(chunk_root, nas_path, use_hull=True):
    print("starting...")
    for file_name in os.listdir(chunk_root): # ['out_982.las']:
        print(f"file {file_name}")
        if file_name.endswith(".las"):
            with laspy.open( os.path.join ( chunk_root, file_name) ) as fh:
                print(f'{file_name} - num_points:', fh.header.point_count)
                if fh.header.point_count < 3:
                    continue

                # count +=1
                # if count > 10:
                #     continue

                lasdata = fh.read().xyz[:,:2] # 2d hull

                mm = min_max(lasdata)

                if use_hull:
                    boundary = convex_hull (lasdata)
                else:
                    boundary = [
                                [mm[0], mm[1]],
                                [mm[0], mm[3]],
                                [mm[2], mm[3]],
                                [mm[2], mm[1]] ]

                if boundary is None: # not enough points for bb
                    continue

                ls = Polygon(boundary)
                origin = Point(round_down( mm[0] ), round_down( mm[1] ) )

                nas_file = f"{nas_path}/{file_name}"

                # https://gis.stackexchange.com/questions/108533/insert-a-point-into-postgis-using-python
                utils.cur.execute(
                    'INSERT INTO las_chunks(geom, type, name, nas, origin)'
                    'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(type)s, %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s) )',
                    {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': file_name, 'nas': nas_file, 'origin': origin.wkb_hex})

    utils.con.commit()

if __name__ == "__main__":

    # chunk_root = "/home/twak/Downloads/meshing_test"
    # nas_path = f"08. Researchers/tom/a14/las_chunks"

    cr = "/08. Researchers/tom/a14/las_chunks"
    nas_path = cr
    chunk_root = f"/home/twak/citnas{cr}"

    curs = setup_db()
    add_chunks_db(chunk_root, nas_path, use_hull=False)

