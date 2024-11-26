import subprocess

import shapely

from api.utils import Postgres
from pathlib import Path
import os
import tarfile
import api.utils as utils
import shapely

"""
The output of build.simple.py is a set of OBJ files, one for each mesh chunk. This script converts them to FBX + tars them.
"""

mesh_table_name = "a14_mesh_chunks"

with Postgres() as pg2:

    pg2.cur.execute(f"""
        SELECT geom, name, nas, files, origin, existence, chunk_size
	    FROM public.a14_mesh_chunks
	    WHERE chunk_size='simple_road-10-50-5x5'
	""")

    for geom, name, nas, files, origin, existence, chunk_size in pg2.cur.fetchall():

        print (f"processing {name}")
        geom = shapely.from_wkb(geom)
        origin = shapely.from_wkb(origin)

        obj_file = f"{utils.nas_mount_w}{nas}/mesh.obj"

        out = subprocess.run(f'cd {Path(__file__).parent.parent.joinpath("blender")} &&'
                             f'/home/twak/lib/blender/blender -b --python blender_obj_to_fbx.py -- '
                             f'--input="{obj_file}"',
                             shell=True, executable='/bin/bash')
        if out.returncode != 0:
            raise Exception("blender failed")

        with tarfile.open(f"{utils.nas_mount_w}{nas}/mesh_fbx.tar", "w") as tar:
            tar.add(f"{utils.nas_mount_w}{nas}/mesh.fbx", arcname=f"mesh/mesh.fbx")

        with Postgres(pass_file="pwd_rw.json") as pg3:
            pg3.cur.execute(f"""
                    INSERT INTO public.{mesh_table_name}(geom, name, nas, files, origin, chunk_size, existence)
                    VALUES ({utils.post_geom(geom)}, '{name}', '{nas}', 'mesh_fbx.tar', {utils.post_geom(origin)}, '{chunk_size}_fbx', '{existence}')
                """)



