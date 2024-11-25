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
Create a simple road mesh from LiDAR data + street centrelines. 
This is Tom's DT/numpy implementation of Leo Binnis's algorithm.
"""

wedge_length = 10
wide, long = 5, 5
tex_scale = 50
out_root = "simple_road"
chunk_size = f"{out_root}-{wedge_length}-{tex_scale}-{wide}x{long}" # database chunk_size column

segment_table_name = "a14_segments"
mesh_table_name = "a14_mesh_chunks2"

def bounds(a, b, c, d):
    bounds = np.concatenate(([a], [b], [c], [d]), axis=0)
    return bounds[:, 0].min(), bounds[:, 0].max(), bounds[:, 1].min(), bounds[:, 1].max()

def build_mesh(pts, id, a, b, c, d, offset):

    global wide, long, tex_scale, out_root

    print(f"building mesh {id}")

    lx, hx, ly, hy = bounds(a, b, c, d)
    uv_range = [hx - lx, hy - ly]

    # compute vertex, uvs, and face indices
    obj_verts, obj_uvs, obj_faces = [], [], []
    for i in range(0, wide):  # ' ol biliear interpolation
        for j in range(0, long):
            obj_verts.append(pts[i][j] - offset)

            uv = (pts[i][j][:2] - [lx, ly])/ uv_range
            # uv[1] = 1 - uv[1]
            obj_uvs.append( uv )

            if i == wide - 1 or j == long - 1:
                continue

            obj_faces.append([i * long + j, (i + 1) * long + j, (i + 1) * long + j + 1])
            obj_faces.append([i * long + j, (i + 1) * long + j + 1, i * long + j + 1])

    name = '{:03d}'.format(id)

    # path = f"/home/twak/Downloads/simple_road/{name}/"
    path = f"{utils.nas_mount_w}{utils.a14_root}{chunk_size}/{name}/"
    os.makedirs(path, exist_ok=True)

    # write out the obj file to disk...
    with open(f"{path}/mesh.obj", "w") as fp:
        fp.write(f"mtllib road.mtl\n")
        fp.write(f"usemtl road\n")
        fp.write(f"o road\n")
        for x in obj_verts:
            fp.write(f"v {x[0]} {x[1]} {x[2]}\n")
        for u in obj_uvs:
            fp.write(f"vt {u[0]} {u[1]}\n")
        for f in obj_faces:
            fp.write(f"f {f[0] + 1}/{f[0] + 1} {f[1] + 1}/{f[1] + 1} {f[2] + 1}/{f[2] + 1}\n")

    with open(f"{path}/road.mtl", "w") as fp:
        fp.write(f"newmtl road\n")
        fp.write(f"Ka 1.0 1.0 1.0\n")
        fp.write(f"Kd 1.0 1.0 1.0\n")
        fp.write(f"Ks 0.0 0.0 0.0\n")
        fp.write(f"Ns 0.0\n")
        fp.write(f"illum 1\n")
        fp.write(f"map_Kd road.png\n")

    # download the textures from geoserver
    urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={lx}&s={ly}&e={hx}&n={hy}&scale={tex_scale}", os.path.join(path, "road.png"))
    urllib.request.urlretrieve(f"{utils.api_url}v0/aerial?w={lx}&s={ly}&e={hx}&n={hy}&scale={tex_scale}", os.path.join(path, "aerial.png"))
    urllib.request.urlretrieve(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_defects_cam&exceptions=application%2Fvnd.ogc.se_inimage&"
        f"SRS=EPSG%3A27700&WIDTH={int((hx - lx)* 100)}&HEIGHT={int((hy - ly)* 100)}"
        f"&BBOX={lx}%2C{ly}%2C{hx}%2C{hy}", os.path.join(path, "defect_mask.png"))

    return name, "mesh.obj;road.mtl;road.png;aerial.png;defect_mask.png"



def find_limits(start, perp_start, las_data):

    p1 = np.array ( [* start + perp_start,0 ] )
    p2 = np.array ( [* start - perp_start,0 ] )

    dist = np.linalg.norm(np.cross( np.c_[las_data[:, :2], np.zeros(las_data.shape[0]) ] - p1, p2-p1), axis=1) / np.linalg.norm(p2 - p1)
    near_line = las_data[dist < 0.5]

    if len(near_line) == 0:
        return None, None

    # let's do this bit in 2d with all points!
    # near_line = las_data
    p1 = np.array ( [* start + perp_start ] )
    p2 = np.array ( [* start ] )
    near_line = near_line[:, :2]

    # project onto distances along line, pick those close to line
    near_line = near_line - p1
    dir = p2 - p1
    proj = np.dot(near_line, dir) / np.dot(dir, dir)

    # compute start and end points
    min = proj[proj.argmin()]
    max = proj[proj.argmax()]

    return p1 + (dir *min), p1 + (dir * max)


def process_wedge(id, poly, start, end, perp_start, perp_end):

    work_dir = Path("/home/twak/Downloads/las_cache")

    # find all las chunks within the wedge-shape
    with Postgres() as pg2:
        pg2.cur.execute(
            f"""
               SELECT name, geom, nas, origin
               FROM public.a14_las_chunks
--                WHERE  ST_Intersects(geom, {utils.post_geom(poly)} )
               WHERE  ST_Intersects(geom, ST_Expand ( {utils.post_geom(poly)}, 0.5) ) -- expand range to ensure computation of start/end lines is same as neighbours
               """
        )

        las_data = np.zeros((0, 4))
        # download each las chunk
        for b in pg2.cur.fetchall():

            chunk_name = b[0]
            chunk_nas = b[2]

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

                xyz = xyz[(xyz[:, 3] == 11)]  # road only
                las_data = np.concatenate((las_data, xyz))

    # a plane to trim points on the wrong side of the road... (no: just use distance from segment for now!)
    psn = -4 * perp_start / np.linalg.norm(perp_start)
    sps = start + psn # go through this point: 4 meters from centreline to meridian...?!
    norm = end - start
    norm /= np.linalg.norm(norm)
    norm = [-norm[1], norm[0]]
    c = -np.dot(norm, sps)

    # trim points on the wrong side of the road
    for plane in [[*norm, c]]:
        las_data = las_data[(las_data[:, 0] * plane[0] + las_data[:, 1] * plane[1] + plane[2]) > 0]

    # we now have a road width with the remaining points
    a,b = find_limits(start, perp_start, las_data)
    c,d = find_limits(end, perp_end, las_data)

    if a is None or d is None:
        print(f"no points found on {id}")
        return

    global wide, long

    # we are going to loop over the road grid and store the x,y,z of each point.
    tol = 0.1  # 10cm height average around each vert
    pts_i = []
    for i in range(0, wide): # ' ol biliear interpolation

        i1 = a + (b - a) * i / (wide-1)
        i2 = c + (d - c) * i / (wide-1)
        pts_j = []
        pts_i.append(pts_j)

        avg_heights = []
        for j in range(0, long):

            pt = i1 + (i2 - i1) * j / (long-1)
            # filter to find las-points around this vertex
            around_pt = las_data[
                         (las_data[:, 0] - tol < pt[0]) &
                         (las_data[:, 0] + tol > pt[0]) &
                         (las_data[:, 1] - tol < pt[1]) &
                         (las_data[:, 1] + tol > pt[1]) ]

            if len(around_pt) == 0:
                height = 0
            else:
                # and average to find the mean height...
                height = around_pt[:,2].mean()
                avg_heights.append(height)

            pts_j.append(np.array([*pt, height]) )

    # patch out-of-bound heights
    mean_height = np.mean(avg_heights)
    for pts_j in pts_i:
        for pt in pts_j:
            if pt[2] == 0:
                pt[2] = mean_height

    # the perimeter of the trimmed wedge, for the database.
    boundary = [a, b, d, c]
    ls = Polygon(boundary)

    lx, hx, ly, hy = bounds(a, b, c, d)
    origin = shapely.Point(lx, ly)

    mesh_file, file_list = build_mesh(pts_i, id, a, b, d, c, [lx,ly,0])

    # insert the new mesh into the database, along with it's boundary.
    with Postgres(pass_file="pwd_rw.json") as pg2:

        global out_root, chunk_size
        pg2.cur.execute(
            f'INSERT INTO public.{mesh_table_name}(geom, name, nas, files, origin, chunk_size, existence) '
            'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(name)s, %(nas)s, %(files)s, ST_SetSRID(%(origin)s::geometry, %(srid)s), %(chunk_size)s, %(existence)s)',
            {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'mesh', 'name': mesh_file, 'nas': f"{utils.a14_root}{chunk_size}/{mesh_file}", 'files': file_list, 'origin': origin.wkb_hex, 'chunk_size': chunk_size, 'existence': utils.before_time_range})

        # pg2.cur.execute(
        #     f"""
        #     INSERT INTO public.tmp (id, geom)
        #     VALUES ({id}, ST_GeomFromText('{ls.wkt}', 27700))
        #     """
        # )
    # with Postgres(pass_file="pwd_rw.json") as pg2:
    #     pg2.cur.execute(
    #         f"""
    #         INSERT INTO public.tmp (id, geom)
    #         VALUES ({id}, ST_GeomFromText('{ls.wkt}', 27700))
    #         """
    #     )


def chunk_path():


    with Postgres(pass_file="pwd_rw.json") as pg2:
        pg2.cur.execute(
            f"""
            DROP TABLE IF EXISTS public.tmp;
            CREATE TABLE public.tmp (id text, geom geometry);
            """)

        if mesh_table_name is not "a14_mesh_chunks":
            pg2.cur.execute(
                f"""
                DROP TABLE IF EXISTS public.{mesh_table_name};
                CREATE TABLE IF NOT EXISTS public.{mesh_table_name}
                (
                    geom geometry(Polygon,27700),
                    name text,
                    nas text,
                    files text,
                    origin geometry(Point,27700),
                    existence tsmultirange,
                    chunk_size text
                );
                """
            )

    count = 0
    # pull the centre-of-road lines from the database
    with (Postgres() as pg):
        pg.cur.execute(f"""
                SELECT  id, geom   
                FROM public.{segment_table_name}
                WHERE id = '6' or id = '2';
                """)

        # for west and east bound roads
        for results in pg.cur.fetchall():
            path = shapely.from_wkb(results[1])
            id = results[0]
            print(f"\nSplitting path id={id}")

            centre_polyline = Polyline(path.wkt).to_lengths(wedge_length)


            extent = 5 # extent of wedge
            for i in range ( len(centre_polyline)-1 ):

                print(f"working on segment {i} of street {id}")

                # compute the shape of the wedge (for las query)
                start = np.array(centre_polyline[i])
                end = np.array(centre_polyline[i + 1])

                perp_start = perp_vector_triple(centre_polyline, i)   * extent
                perp_end = perp_vector_triple(centre_polyline, i + 1) * extent

                a = start + perp_start
                b = end + perp_end
                c = end - perp_end
                d = start - perp_start
                boundary = [a, b, c, d]

                ls = Polygon(boundary)

                perp_start /= np.linalg.norm(perp_start)
                perp_end /= np.linalg.norm(perp_end)

                process_wedge(count, ls, start, end, perp_start, perp_end)
                count += 1

if __name__ == '__main__':
    chunk_path()
