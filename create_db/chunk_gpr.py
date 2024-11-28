import os
import subprocess
from pathlib import Path
import laspy
from shapely.geometry import Polygon, Point
import api.utils as utils

"""
For all las files, this breaks them up into chunks.
"""

def write_file(input_file, out_folder):

    name = Path(input_file).stem
    # scratch = Path(o).pa
    j = os.path.join (out_folder, "go.json")

    with open(j, "w") as fp:
        fp.write(f'''
        [
            "{input_file}",
            {{
                "type":"filters.splitter",
                "length":"10",
                "origin_x":"600000.000",
                "origin_y":"261000.000"
            }},
            {{
                "type":"writers.las",
                "filename":"{out_folder}{name}_#.las"
            }}
        ]
        ''')

    print("merging and filtering point clouds...")
    subprocess.run(f'cd "{out_folder}" && pdal pipeline "{j}"', shell=True, executable='/bin/bash')

table_name="a14_gpr_chunks_tmp"
out = f"{utils.nas_mount_w}/08. Researchers/tom/a14/gpr_chunks_tmp/"
ii  = f"{utils.nas_mount}/06. Data/4. Roads/Cambridge University - National Highways Data/DRF Dataset FULL/05-GPR/GPR-A14EBWBJ47AWoolpittoHaugleyBridge"

if __name__ == "__main__":

    with utils.Postgres(pass_file="pwd_rw.json") as pg:
        curs = pg.cur
        print("removing old table...")
        curs.execute(f'DROP TABLE IF EXISTS {table_name}')
        print("...creating new table...")
        curs.execute(f'CREATE TABLE {table_name} (geom geometry, type text, name text, nas text, origin geometry(Point, {utils.sevenseven}))')

    for filename in os.listdir(ii):
        if filename.endswith(".ply"):
            write_file( os.path.join( ii, filename), out)

    for filename in os.listdir(out):
        f = os.path.join(out, filename)
        if f.endswith(".las"):
            with laspy.open(f) as fh:
                print(f'num_points:', fh.header.point_count)
                if fh.header.point_count < 3:
                    continue

                lasdata = fh.read().xyz[:, :2]  # 2d hull

                mm = utils.min_max(lasdata)

                boundary = [
                    [mm[0], mm[1]],
                    [mm[0], mm[3]],
                    [mm[2], mm[3]],
                    [mm[2], mm[1]]]

                if boundary is None:  # not enough points for bb
                    continue

                ls = Polygon(boundary)
                origin = Point(utils.round_down(mm[0]), utils.round_down(mm[1]))

                with utils.Postgres(pass_file="pwd_rw.json") as pg:
                    pg.cur.execute(
                        f'INSERT INTO {table_name}(geom, type, name, nas, origin)'
                        'VALUES (ST_SetSRID(%(geom)s::geometry, %(srid)s), %(type)s, %(name)s, %(nas)s, ST_SetSRID(%(origin)s::geometry, %(srid)s) )',
                        {'geom': ls.wkb_hex, 'srid': 27700, 'type': 'point_cloud', 'name': filename, 'nas': f, 'origin': origin.wkb_hex})