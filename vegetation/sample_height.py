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

"""
We have a bunch of shape/polyline that doesn't have heights in the database. And are too long.

This script is a first attempt to identify the height from LiDAR data & trim to 200m lengths.

It filters for ground-based points and takes the mean. For points where there is no data, it takes the nearest point.

"""


def integrate_path():

    cachdir = Path("{utils.scratch}/las_cache")
    radius = 1
    seg_count = 1
    table_name = "trace_twixt_lanes_a14"

    # with Postgres(pass_file="pwd_rw.json") as pg:
    #     pg.cur.execute("""
    #         delete from public.a14_vegetation_segments;
    #     """)

    with (Postgres() as pg):
        pg.cur.execute(f"""
            SELECT  id, geom   
            FROM public.{table_name}
--             WHERE id = '14' 
            """ )

        for results in pg.cur.fetchall():

            path = shapely.from_wkb(results[1])
            id = results[0]
            print(f"\nSplitting path id={id}")

            # if id in [29,30,12,21,16]:
            #     print(f"skipping slip road {id}")
            #     continue

            # for seg in Polyline(path.wkt).split_to_lengths(200):
            if True:
                seg = path.geoms[0].coords

                print(f"working on segment {seg}")
                new_coords = []
                for i in range (0,len(seg)):

                    loc = seg[i]
                    # find las chunks around the point and download
                    print (f"looking for las chunks around {loc} - {i} of {len(seg)}")
                    heights = np.zeros((0))

                    if True: # dry run
                        with Postgres() as pg2:
                            pg2.cur.execute(
                                f"""
                                   SELECT type, name
                                   FROM public.a14_las_chunks
                                   WHERE ST_DWithin(geom, ST_SetSRID( 'POINT({loc[0]} {loc[1]})'::geometry, {utils.sevenseven} ) , {radius})
                                   """
                            )

                            if pg2.cur.rowcount > 0:

                                for y in pg2.cur.fetchall():

                                    dest = os.path.join(cachdir, y[1])
                                    src = os.path.join(utils.nas_mount + utils.las_route, y[1])
                                    if os.path.exists(src):
                                        if not os.path.exists(dest):
                                            print(f" >>>> downloading {y[1]}...")
                                            shutil.copy(src, dest)

                                        # read the las chunk with laspy
                                        print (f"reading {y[1]}...")
                                        with laspy.open( dest ) as fh:
                                            lasdata = fh.read()

                                            xyz = np.stack((
                                                lasdata.X * lasdata.header.x_scale,  # move x, y to origin
                                                lasdata.Y * lasdata.header.y_scale,
                                                lasdata.Z * lasdata.header.z_scale,  # height is moved to origin below
                                                lasdata.classification.array,  # we'll use this for filtering out vegetation/cars
                                                np.arange(lasdata.xyz.shape[0])  # index
                                            ), axis=1)

                                            xyz = xyz[(xyz[:, 3] == 2) | (xyz[:, 3] == 7) | (xyz[:, 3] == 8) | (xyz[:, 3] == 9) | (xyz[:, 3] == 11) ]  # road
                                            xyz = xyz[(xyz[:, 0] > loc[0] - radius) & (xyz[:, 0] < loc[0] + radius) & (xyz[:, 1] > loc[1] - radius) & (xyz[:, 1] < loc[1] + radius)]

                                            if xyz.shape[0] > 0:
                                                heights = np.concatenate ((heights, xyz[:, 2]))

                                            # for i, pt in enumerate( lasdata.xyz ): # this can
                                            #     if lasdata.classification[i] in  [2, 7, 8, 9, 11]: # road
                                            #         if math.sqrt((loc[0] - pt[0])**2 + (loc[1] - pt[1])**2) < radius:
                                            #             heights.append(pt[2])

                            print (f"found {len(heights)} heights")
                    else:
                        heights = np.zeros((1))

                    if len(heights) > 0:
                        height = heights.mean()
                    else:
                        height = math.nan

                    new_coords.append ( [loc[0], loc[1], height] )
                    # new_coords.append([loc[0] + random.gauss(0,0.1), loc[1] + random.gauss(0,0.1), height])

                if len (new_coords) < 2:
                    print (f"unable to find sufficient data ({len(new_coords)}) for whole linestring")
                    break

                # create empty list of coords
                valids = list ( filter( lambda x: x[2] is not math.nan, new_coords ) )

                if len (valids) == 0:
                    print(f"unable to find any applicable heights linestring")
                    break

                # assign missing heights as nearest
                for j in range(len(seg)):
                    if new_coords[j][2] is math.nan:
                        best_dist = sys.float_info.max
                        for v in valids:
                            dist = (new_coords[j][0] - v[0])**2 + (new_coords[j][1] - v[1])**2
                            if dist < best_dist:
                                best_dist = dist
                                new_coords[j][2] = v[2]

                if len(new_coords) != len(seg):
                    print("unable to find substitute heights for all points")
                    break

                print(new_coords)

                # now we've found the coordinates for the segment, update the db column
                if new_coords is not None and len(new_coords) > 1:
                    ls = LineString( new_coords )
                    td = LineString ( [[x, y] for [x,y,z] in new_coords] )
                    with Postgres(pass_file="pwd_rw.json") as pg:

                        pg.cur.execute( f"""
                            UPDATE public.{table_name}
                            SET geom_z = ST_GeomFromText('{ls.wkt}', {utils.sevenfour})
                            WHERE id = {id};
                            """)
                    seg_count += 1

if __name__ == '__main__':
    np.seterr(all='raise')
    integrate_path()
