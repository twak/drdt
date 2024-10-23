import urllib
import api.utils as utils
from api.utils import Postgres
import shapely
import numpy as np
import laspy
import random
from numpy.linalg import norm
import math
from shapely.geometry import Polygon, Point
import os

def find_pt_at_dist(path, dist, lengths, l_accum):
    # find a point at a distance along a path
    for i in range (0, len(l_accum)):
        if dist < l_accum[i]:
            extra = (dist - l_accum[i-1]) if i > 0 else dist
            # interpolate between i and i+1
            normal = (path[i+1] - path[i])
            normal = normal / np.linalg.norm(normal)
            perp = np.array([-normal[1], normal[0], 0])

            return (path[i+1] - path[i]) * extra / lengths[i] + path[i], normal, perp

    return path[-1], None, None

def grow_trees_on( seg_name, date = "2024-10-04 17:21:34", las_table="scenario.fred_vege_a14_las_chunks", grown_route = "vege_grown_las/", trees_per_meter=0.05, segment_table="public.a14_vegetation_segments"):

    # print(f"Growing trees on path#{seg_name}")

    with (Postgres() as pg):
        pg.cur.execute(f"""
            SELECT  id, ST_AsText(geom), geom_z,  'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_'               
            FROM {segment_table} WHERE id = '{seg_name}' 
            """ )

        results = pg.cur.fetchone()
        if results[3] == None:
            print("No height info for this segment! run sample_height...")
            return

        path = shapely.from_wkt(results[1])
        path_z = np.array ( shapely.from_wkb(results[2]).coords, dtype=np.float32 )

        lengths, l_accum = [], []

        sofa = 0
        for i in range (0, len(path_z)-1):
            lengths.append( norm ( path_z[i+1] - path_z[i] ) )
            sofa += lengths[-1]
            l_accum.append(sofa)

        for i in range(random.randint(1, max(2,int(sofa*trees_per_meter)))): # number of trees

            print("t", end="")

            dist = random.uniform(0, sofa)
            xyz, _, perp = find_pt_at_dist ( path_z, dist, lengths, l_accum )
            ho = random.uniform(3, 6)
            xyz[2] += ho # height
            xyz += perp * (random.uniform(1, 4) + ho * 0.3)

            radius = max(0.5, random.gauss(3, 1))

            num_pts = int ( 4 * math.pi * radius* 10000 )
            pts = np.random.uniform ( -radius, radius, ( num_pts, 3) )
            pts = pts / np.linalg.norm(pts, axis=1).reshape(-1, 1) * radius * np.random.normal(1, 0.08, (num_pts, 1))

            # dump points to las file
            header = laspy.LasHeader(point_format=3, version="1.2")
            header.offsets = np.zeros(3)
            header.scales = np.array([0.01, 0.01, 0.01]) # las units are in cm
            las = laspy.LasData(header)
            las.xyz = (xyz + pts)
            big = 2**16 -1
            las.red = np.zeros(len(las.points), dtype=np.uint16)
            las.blue = np.zeros(len(las.points), dtype=np.uint16)
            las.red   = (np.random.uniform(0.2, 0.5, len(las.points)) * big).astype(np.uint16)
            las.green = (np.random.uniform(0.3, 0.4, len(las.points)) * big).astype(np.uint16)
            las.blue  = (np.random.uniform(0.1, 0.2, len(las.points)) * big).astype(np.uint16)
            las.classification = np.zeros(len(las.points), dtype=np.uint8) + 5 # high vegetation

            location = f"{utils.nas_mount_w}{utils.a14_root}{grown_route}"
            os.makedirs(location, exist_ok=True)

            las_file, las_name = utils.unique_file(location, f"{seg_name}_{i}" )
            las.write(las_file)

            with Postgres(pass_file="fred.json") as pg:

                # print(f"inserting into db {seg_name}")
                rb = radius * 1.1 # because we wobble the thickness of the shell
                tree_geom = Polygon([ [xyz[0]-rb, xyz[1]-rb], [xyz[0]-rb, xyz[1]+rb], [xyz[0]+rb, xyz[1]+rb], [xyz[0]+rb, xyz[1]-rb] ])
                tree_origin = Point (xyz[0]-rb, xyz[1]-rb)

                pg.cur.execute(
                    f"INSERT INTO {las_table}(geom, type, name, nas, origin, existence) "
                    f"VALUES ({utils.post_geom(tree_geom)}, 'point_cloud', '{las_name}', '{utils.a14_root}{grown_route}{las_name}', "
                    f"{utils.post_geom(tree_origin)}, '{{[{date},]}}' )")



if __name__ == '__main__':
    grow_trees_on("11")