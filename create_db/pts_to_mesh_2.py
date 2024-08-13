import os
import subprocess

"""
For all las files, this breaks them up into chunks.
"""

def write_pdal_file(workdir, las_files, classes, x, y):
    with open(os.path.join ( workdir, "go.json"), "w") as fp:
        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        clst = []
        for c in classes:
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
                    "matrix":"1 0 0 -{x} 0 1 0 -{y} 0 0 1 0 0 0 0 1"
                }},
                {{
                    "type": "writers.ply",
                    "filename": "all.ply"
                }}
                ]
                ''')

#  to write out mesh
tmp = """
                {{
                    "type":"filters.poisson"
                }},
                {{
                    "type":"writers.ply",
                    "faces":true,
                    "filename":"isosurface.ply"
                }}

"""

workdir = "/home/twak/Downloads/d6098df3-bc8e-4696-950e-30cfb4066ef5"
las_files = filter (lambda x : x.endswith(".las"), os.listdir(workdir))
classes = [4,5] # vegetation
write_pdal_file(workdir, las_files, classes, 598555.51,262383.29)

# subprocess.run(["conda", "activate", "pdal"])
# subprocess.run(["pdal", "pipeline", "go.py"])
# os.system(f"cd {workdir} && pdal pipeline go.py")
# os.system(f"conda run -n pdal cd {workdir} && pdal pipeline go.py")