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

wide, long = 10, 10
tex_scale = 10

def build_mesh(pts, id, a, b, c, d):

    global wide, long, tex_scale

    obj_verts, obj_uvs, obj_faces = [], [], []
    for i in range(0, wide):  # ' ol biliear interpolation
        for j in range(0, long):
            obj_verts.append(pts[i][j])
            obj_uvs.append([i / wide, j / long])

            if i == wide - 1 or j == long - 1:
                continue

            obj_faces.append([i * long + j, (i + 1) * long + j, (i + 1) * long + j + 1])
            obj_faces.append([i * long + j, (i + 1) * long + j + 1, i * long + j + 1])

    path = f"/home/twak/Downloads/simple_road/{'{:03d}'.format(id)}/"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/mesh.obj", "w") as fp:
        fp.write(f"mtllib road.mtl\n")
        fp.write(f"usemtl road\n")
        fp.write(f"o road\n")
        for v in obj_verts:
            fp.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for v in obj_uvs:
            fp.write(f"vt {v[0]} {v[1]}\n")
        for v in obj_faces:
            fp.write(f"f {v[0] + 1}/{v[0] + 1} {v[1] + 1}/{v[1] + 1} {v[2] + 1}/{v[2] + 1}\n")

    with open(f"{path}/road.mtl", "w") as fp:
        fp.write(f"newmtl road\n")
        fp.write(f"Ka 1.0 1.0 1.0\n")
        fp.write(f"Kd 1.0 1.0 1.0\n")
        fp.write(f"Ks 0.0 0.0 0.0\n")
        fp.write(f"Ns 0.0\n")
        fp.write(f"illum 1\n")
        fp.write(f"map_Kd road.png\n")

    bounds = np.concatenate((a, b, c, d), axis=0)
    lx, hx, ly, hy = bounds[:, 0].min(), bounds[:, 0].max(), bounds[:, 1].min(), bounds[:, 1].max()

    urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={lx}&s={ly}&e={hx}&n={hy}&scale={tex_scale}", os.path.join(path, "road.png"))
    urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={lx}&s={ly}&e={hx}&n={hy}&scale={tex_scale}", os.path.join(path, "aerial.png"))

def find_limits(start, perp_start, las_data):
    p1 = np.array ( [* start + perp_start, 0] )
    p2 = np.array ( [* start - perp_start, 0] )

    dist = np.linalg.norm(np.cross(p2 - p1, p1 - las_data[:, :3]), axis=1) / np.linalg.norm(p2 - p1)
    near_line = las_data[dist < 0.5]

    # project onto distances along line, pick those close to line
    las_data[:, :3] = near_line[:, :3] - p1
    dir = p2 - p1
    dir /= np.linalg.norm(p2 - p1)
    las_data[:, 3] = np.dot(las_data[:, :3], dir)
    las_data = las_data[las_data[:, 3] < 0.5]

    # compute start and end points
    min = las_data[las_data[:, 3].argmin()][3]
    max = las_data[las_data[:, 3].argmin()][3]

    print(f"min {min} max {max}")

    dir *= (max - min)
    return p1 + dir, p2 + dir


def process_wedge(id, poly, start, end, perp_start, perp_end):

    work_dir = Path("/home/twak/Downloads/las_cache")

    with Postgres() as pg2:
        pg2.cur.execute(
            f"""
               SELECT name, geom, nas, origin
               FROM public.a14_las_chunks
               WHERE ST_Intersects(geom, ST_Expand ( {utils.post_geom(poly)}, 0.5) )
               """
        )

        las_data = np.zeros((0, 4))
        for b in pg2.cur.fetchall():

            chunk_name = b[0]
            chunk_nas = b[2]
            chunk_geom = b[1]
            chunk_origin = b[3]

            print(".", end="")
            # print("processing las chunk", chunk_name)
            dest = os.path.join( work_dir, chunk_name)

            if not os.path.exists(dest):
                print(f"downloading {dest}")
                shutil.copy(utils.nas_mount + chunk_nas, dest)

            with laspy.open(dest) as fh:
                lasdata = fh.read()

                xyz = np.stack((
                    lasdata.X * lasdata.header.x_scale,
                    lasdata.Y * lasdata.header.y_scale,
                    lasdata.Z * lasdata.header.z_scale,  # height is moved to origin below
                    lasdata.classification.array,  # we'll use this for filtering out vegetation/cars
                ), axis=1)

                xyz = xyz[(xyz[:, 3] == 11)]  # road pls
                las_data = np.concatenate((las_data, xyz))

    # a plane to trim points on the wrong side of the road...
    psn = perp_start / np.linalg.norm(perp_start) * 4  # 4 meters from centreline to meridian...?
    sps = start + psn
    norm = end - start
    norm /= np.linalg.norm(norm)
    norm = [norm[1], -norm[0]]
    c = -np.dot(norm, sps)
    for plane in [[*norm, c]]:
        las_data = las_data[(las_data[:, 0] * plane[0] + las_data[:, 1] * plane[1] + plane[2]) > 0]

    # we now have a road las cloud of the points around the grid
    a,b = find_limits(start, perp_start, las_data)
    c,d = find_limits(end, perp_end, las_data)

    global wide, long

    tol = 0.1  # size of sample around point

    pts_i = []
    for i in range(0, wide): # ' ol biliear interpolation

        i1 = a + (b - a) * i / wide
        i2 = c + (d - c) * i / wide
        pts_j = []
        pts_i.append(pts_j)

        for j in range(0, long):

            pt = i1 + (i2 - i1) * j / long
            height = las_data[
                         las_data[:,0]-tol > pt[0] & las_data[:,0]+tol < pt[0] &
                         las_data[:,1]-tol > pt[1] & las_data[:,1]+tol < pt[1]
                         ][:,2].mean()

            pts_j.append(np.array([*pt, height]) )

    build_mesh(pts_i, id, a, b, c, d)


def chunk_path():

    table_name = "a14_segments"

    count = 0
    with (Postgres() as pg):
        pg.cur.execute(f"""
                SELECT  id, geom   
                FROM public.{table_name}
                WHERE id = '6'
                """)

        for results in pg.cur.fetchall():
            path = shapely.from_wkb(results[1])
            id = results[0]
            print(f"\nSplitting path id={id}")

            centre_polyline = Polyline(path.wkt).to_lengths(10)

            extent = 10

            for i in range ( len(centre_polyline)-1 ):

                print(f"working on segment {i} of street {id}")

                start = np.array(centre_polyline[i])
                end = np.array(centre_polyline[i + 1])

                perp_start = perp_vector_triple(centre_polyline, i) * extent
                perp_end = perp_vector_triple(centre_polyline, i + 1) * extent

                a = start + perp_start
                b = end + perp_end
                c = end - perp_end
                d = start - perp_start
                boundary = [a, b, c, d]

                ls = Polygon(boundary)

                process_wedge(count, ls, start, end, perp_start, perp_end)
                count += 1

if __name__ == '__main__':
    chunk_path()
