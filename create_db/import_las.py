import os

import laspy
from pyhull.convex_hull import ConvexHull

import psycopg2
from shapely.geometry import Polygon

chunk_root = "/home/twak/chunks_a14/chunks"

with open("/home/twak/.pass/.postgres") as fp:
    password = fp.read()[:-1]

import api.utils as utils

curs = utils.create_postgres_connection()

curs.execute('DROP TABLE IF EXISTS las_chunks')
curs.execute('CREATE TABLE las_chunks (geom geometry, type text, name text, nas text)')
conn.commit()

count = 0

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


for file_name in os.listdir(chunk_root): # ['out_982.las']:
    if file_name.endswith(".las"):
        with laspy.open( os.path.join ( chunk_root, file_name) ) as fh:
            print(f'{file_name} - num_points:', fh.header.point_count)
            if fh.header.point_count < 3:
                continue

            # count +=1
            # if count > 10:
            #     continue

            lasdata = fh.read().xyz[:,:2] # 2d hull

            hull = convex_hull (lasdata)

            if hull is None:
                continue

            ls = Polygon(hull)

            nas_path = f"/home/twak/citnas/08. Researchers/tom/a14/las_chunks/{file_name}"

            curs.execute(
                'INSERT INTO las_chunks(geom, type, name, nas)'
                'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(type)s, %(name)s, %(nas)s)',
                {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': file_name, 'nas': nas_path})

conn.commit()

# https://gis.stackexchange.com/questions/108533/insert-a-point-into-postgis-using-python