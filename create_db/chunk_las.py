import os

"""
For all las files, this breaks them up into chunks.
"""

def write_file(prefix):
    with open(os.path.join ( "pdal_jsons", prefix+".json"), "w") as fp:
        fp.write(f'''
    [
        "/home/twak/citnas/06. Data/4. Roads/Cambridge University - National Highways Data/DRF Dataset FULL/01-PointClouds/PointCloud-A14EBWBJ47AWoolpittoHaugleyBridge/labelled/HE-PHASE-2_A14_{prefix} - Cloud.las",
        {{
            "type":"filters.splitter",
            "length":"10",
            "origin_x":"600000.000",
            "origin_y":"261000.000"
        }},
        {{
            "type":"writers.las",
            "filename":"chunks/{prefix}_#.las"
        }}
    ]
    ''')


for filename in os.listdir("/home/twak/citnas/06. Data/4. Roads/Cambridge University - National Highways Data/DRF Dataset FULL/01-PointClouds/PointCloud-A14EBWBJ47AWoolpittoHaugleyBridge/labelled"):
    parts = filename.split("_")
    t = parts[3].split(" ")[0]
    os.makedirs( "pdal_jsons", exist_ok=True )
    write_file( f"{parts[2]}_{t}" )