import random
import api.utils as utils
from api.utils import Postgres
import shapely
from shapely.geometry import Polygon, LineString
import numpy as np
from pathlib import Path
import os
import shutil
import laspy
import math
import sys
from vegetation.polyline import Polyline
from api.utils import norm, perp_vector, perp_vector_triple
import urllib.request

"""
Quick hacks to create collision mesh for unreal
"""

def build_collision_mesh():

    table_name = "a14_segments"
    wedge_length = 10

    count = 0
    with (Postgres() as pg):
        pg.cur.execute(f"""
                SELECT  id, geom_z  
                FROM public.{table_name}
                WHERE id = '3'; -- a middlish-located polyline
                """)

        for results in pg.cur.fetchall():

            path = shapely.from_wkb(results[1])
            id = results[0]
            print(f"\nSplitting path id={id}")

            centre_polyline = Polyline(path.wkt).to_lengths(wedge_length)

            extent = 50 # width beyond the edges of the street.
            obj_verts = []

            for i in range ( len(centre_polyline)-1 ):

                print(f"working on segment {i} of street {id}")

                start = np.array(centre_polyline[i])
                end = np.array(centre_polyline[i + 1])

                perp_start = perp_vector_triple(centre_polyline, i)   * extent
                perp_end = perp_vector_triple(centre_polyline, i + 1) * extent

                perp_start = np.array([*perp_start, 0])
                perp_end = np.array([*perp_end, 0])

                a = start + perp_start
                b = end + perp_end
                c = end - perp_end
                d = start - perp_start
                boundary = [a, b, c, d]

                ls = Polygon(boundary)

                perp_start /= np.linalg.norm(perp_start)
                perp_end /= np.linalg.norm(perp_end)

                obj_verts.append(a)
                obj_verts.append(d)

                if i == len (centre_polyline) -2:
                    obj_verts.append(b)
                    obj_verts.append(c)

                count += 1


    obj_faces = []

    for i in range(len(obj_verts)//2-1):
        obj_faces.append([i*2, i*2+1, i*2+2])
        obj_faces.append([i*2+2, i*2+1, i*2+3])

    path = f"{utils.scratch}/collision_mesh"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/mesh.obj", "w") as fp:
        fp.write(f"o road\n")
        for x in obj_verts:
            fp.write(f"v {x[0]} {x[1]} {x[2]}\n")
        for f in obj_faces:
            fp.write(f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}\n")





if __name__ == '__main__':
    build_collision_mesh()
