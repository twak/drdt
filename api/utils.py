import json
import psycopg2
import math
import numpy as np
import os
import subprocess

"""
non-Flask utils
"""

domain = "http://dt.twak.org:5000"
sevenseven = 27700 # bng crs`
sevenfour = 7405 # bng + height crs
cur, con = None, None

# location on the nas that the dt data is stored
a14_root = "/08. Researchers/tom/a14/"

# sub-folders for the various data types
las_route = f"{a14_root}las_chunks"
laso_route = f"{a14_root}laso_chunks"
mesh_route = f"{a14_root}mesh_chunks"
defect_route = f"{a14_root}mesh_defects"
gpr_route = f"{a14_root}gpr_chunks"
gpr_defect_route = f"{a14_root}gpr_defect_chunks"
sign_route = f"{a14_root}signs"

# the location of various local files - update these for your system mounts!
nas_mount = f"/home/twak/citnas" # read only (saftey! - I usually don't mount the writable one on my development box)
nas_mount_w = f"/home/twak/citnas2" # write
blender_binary = "/home/twak/lib/blender/blender"
scratch = "/home/twak/Downloads" # many scripts use this location to write local temporary files. They are often not deleted...but aren't required once copied to the nas.

# the server running the digital twin (can swap these for 129.169.73.137 after tom leaves)
api_url = "http://dt.twak.org:5000/"
geoserver_url = "http://dt.twak.org:8080/"

start_time = "2024-06-10 00:00:00" # the start of now is the day tom joined dr.
before_time_range = '{[2021-01-01,]}' # default creation date for cam-highway data
time_to_sql = "%Y-%m-%d %H:%M:%S"

db_name = "dt01"

class Postgres():
    def __init__(self, pass_file="pwd.json"):
        self.pass_file = pass_file
        self.cur, self.con = None, None

    def __enter__(self):

        with open(f"api/{self.pass_file}") as fp:
            pwp = json.load(fp)

        # print(f"connecting to {pwp['dbname']}@{pwp['host']}")
        self.con = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
        self.cur = self.con.cursor()
        # print(f"success as {pwp['user']}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.con.commit()
        self.con.close()


def create_postgres_connection(pass_file="pwd.json"):
    global curs
    with open(f"api/{pass_file}") as fp:
        pwp = json.load(fp)

    global cur, con
    print(f"connecting to {pwp['dbname']}@{pwp['host']}")
    con = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
    cur = con.cursor()
    print(f"success as {pwp['user']}")

    return cur, con

def ro_create_postgres_connection():
    global curs
    with open("api/pwd.json") as fp:
        pwp = json.load(fp)

    global cur, con
    con = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
    cur = con.cursor()
    return curs, con


def min_max (lasdata):

    return (lasdata[:,0].min(), lasdata[:,1].min(), lasdata[:,0].max(), lasdata[:,1].max() )


def round_down (x):
    return math.floor(x/10)*10

def build_commond_state():

    scenario_name, vals, _ = get_scenario()

    if vals is not None: # error
        return vals, scenario_name

    vals = get_nsew()
    if isinstance(vals, str):
        return vals, None

    return vals, scenario_name


def get_scenario (api_key=None):

    vals = None # error message
    scenario_name = None
    user = None

    with Postgres() as pg:

        if api_key is None:
            api_key = request.args.get('api_key', None)

        if api_key is not None:

            # user = scenarios.request_loader(request)
            # if user is None:
            #     vals = f"bad key"

            pg.cur.execute(
                f"SELECT scenario, human_name FROM public.scenarios WHERE api_key = '{api_key}'") # AND human_name='{user.id}'

            row = pg.cur.fetchone()

            if row:
                scenario_name = row[0]
                user = row[1]
            else:
                vals = f"bad api key"

    return scenario_name, vals, user


def envelope(vals):
    return (f"ST_MakeEnvelope({vals['w']}, {vals['s']}, {vals['e']}, {vals['n']}, 27700 )::geometry('POLYGON')")

def get_nsew(other=[],opt={}):
    vals = {}
    for x in ['n', 'w', 's', 'e']+other:
        if not x in request.args:
            return f"missing parameters {x}"
        vals[x]= request.args[x]

    for x in opt.keys():
        if x in request.args:
            vals[x] = request.args[x]
        else:
            vals[x] = opt[x]

    return vals


def unique_file(location, stub, extn="las"):
    # find unique filename
    j = 0
    while (True):
        name = f"{stub}{'' if j == 0 else '_' + str(j)}.{extn}"
        f = os.path.join(location, name)
        if not os.path.exists(f):
            break

        j = j + 1
    return f, name


def post_geom(geom, srid=sevenseven):
    """
    string for postgres
    """
    return f"ST_SetSRID('{geom.wkb_hex}'::geometry, {srid})"


    def do_pdal(self, name, las_files, workdir):

        with open(os.path.join ( workdir, f"go.json"), "w") as fp:

            fp.write("[\n")
            for f in las_files:
                fp.write(  f'"{f}", \n')

            fp.write(f'''
                    {{
                        "type": "filters.merge"
                    }},
                    {{
                        "type": "writers.las",
                        "filename": "{name}.las"
                    }}
                    ]
                    ''')

        # this requires pdal in the current path (use conda!)
        print("pdaling merging and filtering point clouds...")
        subprocess.run(f'cd {workdir} && pdal pipeline go.json', shell=True, executable='/bin/bash')


def merge_las_files( name, las_files, workdir, cull=None, format="las"):


    randomize_filter = f"""
    {{
        "type":"filters.randomize"
    }},
    """ if cull else ""

    cull_filter = f"""
    {{
        "type":"filters.decimation",
        "step": {cull}
    }},
    """ if cull else ""


    with open(os.path.join ( workdir, f"go.json"), "w") as fp:

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        fp.write(f'''
                {{
                    "type": "filters.merge"
                }},
                {randomize_filter}
                {cull_filter}
                {{
                    "type": "writers.{format}",
                    "filename": "{name}.{format}"
                }}
                ]
                ''')

    # this requires pdal in the current path (use conda!)
    print("pdaling merging and filtering point clouds...")
    subprocess.run(f'cd "{workdir}" && pdal pipeline go.json', shell=True, executable='/bin/bash')

    return f"{name}.las"


def norm(v):
    return v / np.linalg.norm(v)

def perp_vector(a, b):
    v = norm(np.array([b[0] - a[0], b[1] - a[1]]))
    return np.array([-v[1], v[0]])

def perp_vector_triple(linestring, i):
    # def perp_vector_triple(a, b, c):

    a = linestring[i - 1] if i > 0 else None
    b = linestring[i]
    c = linestring[i + 1] if i < len(linestring) - 1 else None

    if c is None:
        return perp_vector(a, b)
    elif a is None:
        return perp_vector(b, c)
    else:
        v1 = perp_vector(a, b)
        v2 = perp_vector(b, c)
        out = (v1 + v2)
        out = out / np.linalg.norm(out)
        return out

