import sys

import shapely

import api.utils as utils
from api.utils import Postgres
from shapely import wkb, Polygon, Point
import shutil, os
import urllib.request
import uuid
import subprocess
from pathlib import Path

"""
for each pothole shape we create a mesh:
 - download shapefile + grow by 20cm
 - download all nearby las files
 - download texture
 - use pdal to merge, filter, and crop point cloud to shape
 - use blender to create a mesh + insert into new database.
"""

def run_pdal_scripts(workdir, las_files, x, y, area ):

    out_folder = "stage2"

    klass = "defect"

    with open(os.path.join ( workdir, out_folder, f"go_{klass}.json"), "w") as fp:

        print (f"generating {klass}")

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"stage1/{f}", \n')

        clst = []
        for c in [2, 7, 8, 9, 11]:
            clst.append( f"Classification[{c}:{c}]" )
        clst = ", ".join( clst )

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
                    "polygon":"{area}"
                }},
                {{
                    "type":"filters.transformation",
                    "matrix":"1 0 0 -{x} 0 1 0 -{y} 0 0 1 {-50} 0 0 0 1"
                }},
                {{
                    "type": "writers.ply",
                    "filename": "{out_folder}/{klass}.ply"
                }}
                ]
                ''')

    # this requires pdal in the current path (use conda!)
    print("merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline {out_folder}/go_{klass}.json', shell=True, executable='/bin/bash')


def merge_and_filter_pts( workdir, x, y, area ):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(os.path.join(workdir, "stage1" ) ) ) )

    run_pdal_scripts(workdir, las_files, x,y, area )

def run_blender( workdir ):

    # call blender to run the meshing script from its directory
    workdir = Path(workdir)
    print("running blender...")

    out = subprocess.run(f'cd {Path(__file__).parent.parent.joinpath("blender")} &&'
                   f'{utils.blender_binary} -b pts_to_defect_mesh.blend --python blender_pts_to_defect_mesh.py -- '
                   f'--cycles-device OPTIX --root="{workdir.parent}" --name="{workdir.name}"',
                   shell=True, executable='/bin/bash')

    return out.returncode

def go():

    mesh_chunks = f"{utils.nas_mount_w}{utils.defect_route}"
    table_name = "a14_mesh_defects"
    # chunk_size = 10
    scratch = f"{utils.scratch}/foo"

    with Postgres(pass_file="pwd_rw.json") as pg:

        # pg.cur.execute(f'DROP TABLE IF EXISTS {table_name}')
        # pg.cur.execute(
        #     f'CREATE TABLE {table_name} (id PRIMARY KEY, geom geometry(Polygon, {utils.sevenseven}), buffer geometry(Polygon, {utils.sevenseven}), name text, nas text, files text, origin geometry(Point, {utils.sevenseven}))')
        # pg.con.commit()

        pg.cur.execute(
            f"""
            SELECT geom, id, type, layer
            FROM public.a14_defects_cam
--             WHERE ST_DWithin(geom, ST_SetSRID( ST_MakePoint(598555.51,262383.29), 27700 ) , 1)
            """)

        for x in pg.cur:

            try:
                geom = wkb.loads(x[0])
                id = x[1]
                type = x[2]
                layer = x[3]

                bounds = shapely.bounds(geom)
                buffer = geom.buffer(0.2, cap_style='flat')
                buffer_bounds = shapely.bounds(buffer)
                origin = buffer_bounds[:2]

                print (f" type: {type} name: {layer}")

                c2 = pg.con.cursor()

                # if no origin in mesh_chunks database, then.

                # workdir = os.path.join (utils.nas_mount+utils.mesh_route, f"{origin.x}_{origin.y}" )
                pothole_name = f"w_{id}" # _w_indows friendly filename
                workdir = os.path.join (scratch, pothole_name )

                if os.path.exists(f"{mesh_chunks}/{pothole_name}"):
                    print("output already exists, skipping")
                    continue # guess we've already done this

                os.makedirs(workdir, exist_ok=True)

                for i in range (1,4):
                    os.makedirs( os.path.join ( workdir, f"stage{i}"), exist_ok=True)

                c2.execute (
                    f"""
                    SELECT type,name, geom
                    FROM public.a14_las_chunks
                    WHERE ST_Intersects(geom, ST_SetSRID( '{buffer.wkb_hex}'::geometry, 27700 ) )
                    """
                )

                # download nearby las files
                for y in c2:
                    print (f" >>>> downloading {y[1]}...")
                    dest = os.path.join(workdir, "stage1", y[1])
                    if not os.path.exists(dest):
                        shutil.copy (os.path.join (utils.nas_mount+utils.las_route, y[1]), dest )

                # run pdal, merge and filter point clouds
                merge_and_filter_pts (workdir, origin[0], origin[1], buffer.wkt)

                # download textures
                # urllib.request.urlretrieve(f"{utils.api_url}v0/pavement?w={buffer_bounds[0]}&s={buffer_bounds[1]}&e={buffer_bounds[2]}&n={buffer_bounds[3]}&scale=100", os.path.join(workdir, "stage2", "pavement.png"))

                scale = 300
                w, h = int ( scale * (buffer_bounds[2] - buffer_bounds[0])), int ( scale * (buffer_bounds[3] - buffer_bounds[1] ))
                urllib.request.urlretrieve( f"{utils.geoserver_url}geoserver/ne/wms?service=WMS&version=1.1.0&request=GetMap&layers=ne%3AA14_pavement_orthomosaics&bbox={buffer_bounds[0]}%2C{buffer_bounds[1]}%2C{buffer_bounds[2]}%2C{buffer_bounds[3]}&"
                                            f"width={w}&height={h}&srs=EPSG%3A27700&styles=&format=image%2Fjpeg", os.path.join(workdir, "stage2", "pavement.jpg"))

                # create fbx files
                file_str = []
                if run_blender( workdir ) == 0:

                    to = os.path.join ( mesh_chunks, pothole_name )

                    os.makedirs(to, exist_ok=True)
                    for f in os.listdir(os.path.join(workdir, "stage3")):
                        print (f"copying mesh file {f} to nas...")
                        shutil.copyfile( os.path.join(workdir, "stage3", f), os.path.join(to, f) )
                        file_str.append(f)

                    file_str = ";".join(file_str)

                    origin = Point(origin[0], origin[1])


                    print("updating db...")
                    c2.execute(
                        f"UPDATE public.a14_defects_cam SET "
                        f"buffer = ST_SetSRID('{buffer.wkb_hex}'::geometry, {utils.sevenseven}), "
                        f"origin = ST_SetSRID('{origin.wkb_hex}'::geometry, {utils.sevenseven}), "
                        f"name   = '{pothole_name}', "
                        f"nas    = '{utils.defect_route}/{pothole_name}', "
                        f"files  = '{file_str}' "
                        f"WHERE id = {id};" )
                        # f'INSERT INTO {table_name}(geom, buffer, name, nas, files, origin) '
                        # 'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(name)s, %(nas)s, %(files)s, ST_SetSRID(%(origin)s::geometry, %(srid)s) )',
                        # {'geom': geom.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': chunk_name, 'nas': f"{utils.mesh_route}/{chunk_name}", 'files':file_str, 'origin': origin.wkb_hex})

                    pg.con.commit()


                shutil.rmtree(workdir)
            except Exception as e:
                print (f"failed to process {x[1]} {e}")



if __name__ == "__main__":
    go()