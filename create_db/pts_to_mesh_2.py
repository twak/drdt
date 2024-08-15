import os
import subprocess

"""
For all las files, this breaks them up into chunks.
"""

def run_pdal_scripts(workdir, las_files, classes, x, y):

    out_folder = "stage2"

    for klass in classes.keys():
        # out_folder = os.path.join ( workdir, out_folder )
        os.makedirs(out_folder, exist_ok=True)
        with open(os.path.join ( workdir, out_folder, f"go_{klass}.json"), "w") as fp:

            print (f"generating {klass}")

            fp.write("[\n")
            for f in las_files:
                fp.write(  f'"stage1/{f}", \n')

            clst = []
            for c in classes.get(klass):
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
        subprocess.run(f'cd {workdir} && pdal pipeline {out_folder}/go_{klass}.json', shell=True, executable='/bin/bash')


def merge_and_filter_pts(workdir="/home/twak/Downloads/d6098df3-bc8e-4696-950e-30cfb4066ef5/",  x=598555.51,y=262383.29):

    las_files = list ( filter (lambda x : x.endswith(".las"), os.listdir(os.path.join(workdir, "stage1" ) ) ) )
    classes = {}
    classes["vegetation"] = [3, 4, 5]
    classes["road"] = [2, 7, 8, 9, 11]
    run_pdal_scripts(workdir, las_files, classes, x,y )


if __name__ == "__main__":
    merge_and_filter_pts()