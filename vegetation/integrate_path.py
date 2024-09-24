
import api.utils as utils
from api.utils import Postgres
import shapely
from shapely.geometry import Polygon
from shapely import to_geojson
import numpy as np
from pathlib import Path
import os
import shutil
import subprocess
import laspy
import matplotlib.pyplot as plt
from PIL import Image

"""
Given a linestring ( a road segment ) we, for each line therin, and compute a wedge shape around it. 
We then download all las files within that wedge, orient them along the line, and add them to a density image.

The output for the road segment is then a vegetation density pointcloud.
"""


def add_to_result(result, array):

    resolution = 10

    width = result.shape[1]
    height = result.shape[0]
    mid = width // 2

    # vertical_offset = np.percentile ( array[0], 10 ) # we don't have road height, so adjust "dynamically"
    vertical_offset = 0

    array[1] = ( array[1] * resolution ) + mid # x move to the middle of the image
    array[0] = ( ( array[0] - vertical_offset ) * resolution ) + height//10 # z move a little off the bottom of the image
    array = array.astype(int)

    array[0] = array[0].clip(0, height-1)
    array[1] = array[1].clip(0, width-1)

    for z, x in zip(array[0], array[1]):
        result[height-1-z, x] += 1


def render (path, array):

    resolution = 10 # px per meter

    rw = int(array[0].max() - array[0].min())
    rh = int(array[1].max() - array[1].min())

    array[0] = ((array[0] - array[0].min()) * resolution).clip(0, rw * resolution)
    array[1] = ((array[1] - array[1].min()) * resolution).clip(0, rh * resolution)

    array = array.astype(int)

    r = np.zeros((rw * resolution + 1, rh * resolution + 1))

    for x, y in zip(array[0], array[1]):
        r[rw* resolution - 1- x,y] += 1

    cutoff = np.percentile(r, 95)
    r = 255 - (r * 255 / cutoff).clip(0, 255)

    im = Image.fromarray(r.astype(np.uint8))

    im.save(path)

def do_pdal(name, las_files, start, end, ls, transform, workdir):

    with open(os.path.join ( workdir, f"go.json"), "w") as fp:

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        clst = []
        for c in [3, 4, 5]: # vegetation
            clst .append( f"Classification[{c}:{c}]" )

        clst = ", ".join(clst)

        fp.write(f'''
                {{
                    "type": "filters.merge"
                }},
                {{
                    "type":"filters.range",
                    "limits":"{clst}"
                }},
                {{
                    "type":"filters.crop",
                    "polygon":"{ls.wkt}"
                }},
                {{
                    "type":"filters.transformation",
                    "matrix":"{transform}"
                }},

                {{
                    "type": "writers.las",
                    "filename": "out.las"
                }}
                ]
                ''')


    # this requires pdal in the current path (use conda!)
    print("pdaling merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline go.json', shell=True, executable='/bin/bash')

def norm(v):
    return v / np.linalg.norm(v)

def perp_vector(a, b):
    v = norm ( np.array([b[0] - a[0], b[1] - a[1]]) )
    return np.array([-v[1], v[0]])

def perp_vector_triple(linestring, i):
# def perp_vector_triple(a, b, c):

    a = linestring[i - 1] if i > 0 else None
    b = linestring[i]
    c = linestring[i + 1] if i < len(linestring) - 1 else None

    if c == None:
        return perp_vector(a, b)
    elif a == None:
        return perp_vector(b, c)
    else:
        v1 = perp_vector(a, b)
        v2 = perp_vector(b, c)
        out = (v1 + v2 )
        out = out / np.linalg.norm(out)
        return out

def integrate_path(seg_name):

    print("Integrating path: ", seg_name)

    # workdir = Path("/home/twak/Downloads/geojsons")
    workdir = Path("/home/twak/Downloads/las_cache")

    # the output image. we add to it for each segment of the line (and wedge to lidar)
    result = np.zeros((200, 1000))

    with Postgres() as pg:
        pg.cur.execute(f"""
            SELECT  id, ST_AsText(geom), geom_z,  'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_'               
            FROM public.a14_segments WHERE id = '{seg_name}' 
            """ )

        results = pg.cur.fetchone()
        if results[2] == None:
            print("No height info for this segment! run sample_height...")
            return
        path = shapely.from_wkt(results[1])
        path_z = shapely.from_wkb(results[2])



        print(path)

        for lsi, linestring in enumerate(path.geoms):

            extent = 100 # how far does the wedge extend from the segment

            # for each line segment, create an envelope. we expect a single linestring per geometry.
            for i in range (len(linestring.coords)-1):

                print (f"processing segment {i} of {len(linestring.coords)-1}")

                name = seg_name+str(i)

                start =  np.array(linestring.coords[i])
                end =  np.array(linestring.coords[i+1])
                sh = path_z.coords[i][2]
                eh = path_z.coords[i+1][2]

                mid = (start + end) / 2

                to_origin = np.array([
                    [1, 0, 0, -mid[0]],
                    [0, 1, 0, -mid[1]],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1]])

                perp_start = perp_vector_triple(linestring.coords, i) * extent
                perp_end = perp_vector_triple(linestring.coords, i+1) * extent

                a = start + perp_start
                b = end + perp_end
                c = end - perp_end
                d = start - perp_start

                boundary = [ a, b, c ,d ]
                ls = Polygon(boundary)
                # filepath = Path(f"/home/twak/Downloads/geojsons/path_{i}.geojson")

                print (ls)

                with Postgres() as pg2:
                    pg2.cur.execute(
                        f"""
                        SELECT type, name
                        FROM public.a14_las_chunks
                        WHERE ST_DWithin(geom, ST_SetSRID( '{ls.wkb_hex}'::geometry, {utils.sevenseven} ) , 10)
                        """
                    )

                    lases = []

                    for y in pg2.cur.fetchall():
                        dest = os.path.join(workdir, y[1])
                        lases.append(y[1])
                        if not os.path.exists(dest):
                            print(f" >>>> downloading {y[1]}...")
                            shutil.copy ( os.path.join(utils.nas_mount + utils.las_route, y[1]), dest )

                    v1 = [*norm ( end - start ), 0]
                    v2 = [*perp_vector(start, end), 0]
                    v3 = np.array([0, 0, 1])

                    # rotate cloud to lie along y axes
                    rotate = np.array([[v2[0], v1[0], v3[0], 0],
                                       [v2[1], v1[1], v3[1], 0],
                                       [v2[2], v1[2], v3[2], 0],
                                       [0, 0, 0, 1]])

                    # and move to origin
                    t = np.matmul(rotate, to_origin)

                    # fixme: this is very low resolution - we should transform the las files to the origin with utils.offset_las()
                    do_pdal ( name, lases, start, end, ls, " ".join ( list ( map (str, t.flatten()) ) ), workdir )

                with laspy.open(os.path.join(workdir, f"out.las")) as fh:
                    lasdata = fh.read().xyz
                    # render( os.path.join(workdir, f"out_{i}.png"), np.stack ( [ lasdata [:,2] , lasdata [:,0]] ) )

                    length = np.linalg.norm(end - start)

                    lasdata[:,2] -= sh + (eh - sh) * (lasdata[:,1] + length/2) / length # linear interpolatation for height

                    add_to_result (result,np.stack ( [ lasdata [:,2] , lasdata [:,0]] ) )

                cutoff = np.percentile(result, 95)
                r = 255 - (result * 255 / cutoff).clip(0, 255)
                im = Image.fromarray(r.astype(np.uint8))
                im.save( os.path.join("/home/twak/Downloads", f"out{i}.png") )

                # if i == 2:
                #     break

                # return




if __name__ == '__main__':
    integrate_path("11")