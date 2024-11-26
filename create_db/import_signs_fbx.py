from pathlib import Path
import subprocess
import pywavefront
from pyhull.convex_hull import ConvexHull # note latest pyhull crashs my pc, I had to install an older one
import numpy as np

from api.utils import Postgres
from shapely.geometry import Polygon, Point
import api.utils as utils

def convex_hull(lasdata, file_name):
    try:
        hull = ConvexHull(lasdata.tolist())
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

    return np.array ( list(map(lambda x: lasdata[x], loop + [loop[0]])))  # map index to coords; last point is first

def get_bounds(fbx_file):

    obj_file = Path(fbx_file).with_suffix(".obj")
    if not Path(obj_file).exists():
        out = subprocess.run(f'cd {Path(__file__).parent.parent.joinpath("blender")} &&'
                             f'{utils.blender_binary} -b  --python blender_fbx_to_obj.py -- '
                             f'--cycles-device OPTIX --input="{fbx_file}"',
                             shell=True, executable='/bin/bash')
        if out.returncode != 0:
            raise Exception("blender failed")

    scene = pywavefront.Wavefront(obj_file)
    # print (scene.vertices)
    verts = np.array(scene.vertices)

    return convex_hull(verts[:,[0,2]], fbx_file), verts[:,2].min()

if __name__ == '__main__':

    table_name="a14_signs"

    with Postgres(pass_file="pwd_rw.json") as pg:
        pg.cur.execute(f"""
            DELETE FROM {table_name}
        """)
        pg.con.commit()

    offsets = []
    with open ("/home/twak/Documents/signs/locs.csv") as f:
        for line in f:
            parts = line.strip().split(",")
            offsets.append([float(parts[0]), float(parts[1]), float(parts[2])])

    path = "/home/twak/Documents/signs/clean"

    with Postgres(pass_file="pwd_rw.json") as pg:
        for i in range (1, 11):
            name = f"{'{:03d}'.format(i)}.fbx"
            fbx_file = f"{path}/{name}"
            bounds, minZ = get_bounds(fbx_file)
            offset = offsets[i-1]
            bounds = bounds + offset[:2]

            ls = Polygon(bounds)
            origin = Point(offset)
            nas_file = f"{utils.sign_route}/{name}"

            # https://gis.stackexchange.com/questions/108533/insert-a-point-into-postgis-using-python
            pg.cur.execute(f"""
                INSERT INTO {table_name}(geom, type, name, nas, origin, existence)
                VALUES ({utils.post_geom(ls)}, 'mesh', '{name}', '{nas_file}', {utils.post_geom(origin, srid=utils.sevenfour)}, '{utils.before_time_range}' )
            """)