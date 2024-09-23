import api.utils as utils
from api.utils import Postgres
import shapely
from shapely.geometry import Polygon, LineString
from shapely import to_geojson
import numpy as np
from pathlib import Path
import os
import shutil
import subprocess
import laspy
import matplotlib.pyplot as plt
from PIL import Image
import math

"""
We have a bunch of data that doesn't have heights in the database.

This script is a first attempt to identify the height from LiDAR data.

"""


def integrate_path():

    cachdir = Path("/home/twak/Downloads/las_cache")
    radius = 1

    with (Postgres() as pg):
        pg.cur.execute(f"""
            SELECT  id, ST_AsText(geom), 'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_'               
            FROM public.a14_segments
            WHERE id = '11' 
            """ )


        results = pg.cur.fetchone()
        path = shapely.from_wkt(results[1])
        id = results[0]

        print("Integrating paths", id)

        for linestring in path.geoms:
            new_coords = []

            for i in range (len(linestring.coords)-1):

                loc = np.array(linestring.coords[i])

                # find las chunks around the point and download

                with Postgres() as pg2:
                    pg2.cur.execute(
                        f"""
                           SELECT type, name
                           FROM public.a14_las_chunks
                           WHERE ST_DWithin(geom, ST_SetSRID( 'POINT({loc[0]} {loc[1]})'::geometry, {utils.sevenseven} ) , {radius})
                           """
                    )

                    if pg2.cur.rowcount > 0:

                        heights = []

                        for y in pg2.cur.fetchall():

                            dest = os.path.join(cachdir, y[1])
                            if not os.path.exists(dest):
                                print(f" >>>> downloading {y[1]}...")
                                shutil.copy(os.path.join(utils.nas_mount + utils.las_route, y[1]), dest)

                            # read the las chunk with laspy
                            with laspy.open( dest ) as fh:
                                lasdata = fh.read()

                                lasdata = lasdata[lasdata.classification in [2]]  # ground points

                                for pt in lasdata.xyz:
                                    if math.sqrt((loc[0] - pt[0])**2 + (loc[1] - pt[1])**2) < radius:
                                        heights.append(pt[2])

                            if len(heights) > 0:
                                height = sum(heights) / len(heights)

                new_coords.append((loc[0], loc[1], height))

            if len (new_coords) < 2:
                print (f"unable to find sufficient data ({len(new_coords)}) for whole linestring")
                return

            # create empty list of coords
            valids = list ( filter( lambda x: x[2] is not math.nan, new_coords ) )

            # assign missing heights as nearest
            for j in range(len(linestring.coords) - 1):
                if new_coords[j][2] is math.nan:
                    best_dist = 1000000
                    for k in range(len(valids)):
                        dist = (new_coords[j][0] - valids[k][0])**2 + (new_coords[j][1] - valids[k][1])**2
                        if dist < best_dist:
                            best_dist = dist
                            new_coords[j][2] = valids[k][2]

        print(new_coords)

        # now we've found the coordinates for the segment, update the db column
        ls = LineString( new_coords )
        with Postgres(pass_file="pwd_rw.json") as pg:
            pg.cur.execute( f"""
                UPDATE public.a14_segments
                SET geom_z=ST_SetSRID('{ls.wkb_hex}'::geometry, {utils.sevenseven})
                WHERE id = '{id}'
                """)

if __name__ == '__main__':
    integrate_path()
