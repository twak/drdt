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

    cachdir = Path("/home/twak/Downloads/las_cache")
    radius = 1

    with (Postgres() as pg):
        pg.cur.execute(f"""
            SELECT  id, ST_AsText(geom), 'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_'               
            FROM public.a14_segments
            WHERE id != '14' 
            """ )

        for results in pg.cur.fetchall():

            path = shapely.from_wkt(results[1])
            id = results[0]
            print("Integrating paths", id)

            new_coords = []

            if len ( path.geoms ) != 1:
                raise Exception("path is not a single linestring")


            for linestring in Polyline(path.wkt).split_to_lenghts(200):

                for i in range (len(linestring.coords)):

                    loc = np.array(linestring.coords[i])

                    # find las chunks around the point and download
                    print (f"looking for las chunks around {loc} - {i} of {len(linestring.coords)}")

                    if True:
                        with Postgres() as pg2:
                            pg2.cur.execute(
                                f"""
                                   SELECT type, name
                                   FROM public.a14_las_chunks
                                   WHERE ST_DWithin(geom, ST_SetSRID( 'POINT({loc[0]} {loc[1]})'::geometry, {utils.sevenseven} ) , {radius})
                                   """
                            )

                            heights = []

                            if pg2.cur.rowcount > 0:

                                for y in pg2.cur.fetchall():

                                    dest = os.path.join(cachdir, y[1])
                                    src = os.path.join(utils.nas_mount + utils.las_route, y[1])
                                    if os.path.exists(src):
                                        if not os.path.exists(dest):
                                            print(f" >>>> downloading {y[1]}...")
                                            shutil.copy(src, dest)

                                        # read the las chunk with laspy
                                        with laspy.open( dest ) as fh:
                                            lasdata = fh.read()

                                            for i, pt in enumerate( lasdata.xyz ): # this can
                                                if lasdata.classification[i] in  [2, 7, 8, 9, 11]: # road
                                                    if math.sqrt((loc[0] - pt[0])**2 + (loc[1] - pt[1])**2) < radius:
                                                        heights.append(pt[2])

                            print (f"found {len(heights)} heights")

                        if len(heights) > 0:
                            height = sum(heights) / len(heights)
                        else:
                            height = math.nan

                    new_coords.append([loc[0], loc[1], height])

                if len (new_coords) < 2:
                    print (f"unable to find sufficient data ({len(new_coords)}) for whole linestring")
                    new_coords = None
                    break

                # create empty list of coords
                valids = list ( filter( lambda x: x[2] is not math.nan, new_coords ) )

                if len (valids) == 0:
                    print(f"unable to find any applicable heights linestring")
                    new_coords = None
                    break

                # assign missing heights as nearest
                for j in range(len(linestring.coords)):
                    if new_coords[j][2] is math.nan:
                        best_dist = sys.float_info.max
                        for v in valids:
                            dist = (new_coords[j][0] - v[0])**2 + (new_coords[j][1] - v[1])**2
                            if dist < best_dist:
                                best_dist = dist
                                new_coords[j][2] = v[2]

                if len(new_coords) != len(linestring.coords):
                    new_coords = None

            print(new_coords)

            # now we've found the coordinates for the segment, update the db column
            if new_coords is not None:
                ls = LineString( new_coords )
                with Postgres(pass_file="pwd_rw.json") as pg:
                    pg.cur.execute( f"""
                        INSERT INTO public.a14_vegetation_segments (id, geom, 'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_' , geom_z)
                        VALUES (geom_z= ST_GeomFromText('{ls.wkt}', {utils.sevenfour})
                        WHERE id = '{id}'
                        """)

if __name__ == '__main__':
    integrate_path()
