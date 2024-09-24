import json
import psycopg2
import math
import laspy
import flask
from flask import request
from . import scenarios, app

domain = "http://dt.twak.org:5000"
sevenseven = 27700 # bng crs
sevenfour = 7405 # bng + height crs
cur, con = None, None

a14_root = "/08. Researchers/tom/a14/"

las_route = f"{a14_root}las_chunks"
laso_route = f"{a14_root}laso_chunks"
mesh_route = f"{a14_root}mesh_chunks"
defect_route = f"{a14_root}mesh_defects"
gpr_route = f"{a14_root}gpr_chunks"
gpr_defect_route = f"{a14_root}gpr_defect_chunks"
nas_mount = f"/home/twak/citnas" # read only
nas_mount_w = f"/home/twak/citnas" # write

api_url = "http://dt.twak.org:5000/"
geoserver_url = "http://dt.twak.org:8080/"

start_time = "2024-06-10 00:00:00" # the start of now is the day tom joined dr.
before_time_range = '{[2021-01-01,]}' # default creation date for cam-highway data

table_name = "dt01"

class Postgres():
    def __init__(self, pass_file="pwd.json"):
        self.pass_file = pass_file
        self.cur, self.con = None, None

    def __enter__(self):

        with open(f"api/{self.pass_file}") as fp:
            pwp = json.load(fp)

        print(f"connecting to {pwp['dbname']}@{pwp['host']}")
        self.con = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
        self.cur = self.con.cursor()
        print(f"success as {pwp['user']}")
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

def offset_las (lasfile, x, y):

    las = laspy.read(lasfile)

    las.header.offset = [x, y, 0]

    with laspy.open(lasfile, mode="w", header=las.header) as writer:
        writer.write_points(las.points)


def build_commond_state():

    vals = get_nsew()

    if isinstance(vals, str):
        return vals, None

    scenario_name = None
    user = None

    with Postgres() as pg:

        api_key = request.args.get('api_key', None)
        if api_key is not None:

            user = scenarios.request_loader(request)
            if user is None:
                vals = f"bad key"

            pg.cur.execute(
                f"SELECT scenario FROM public.scenarios WHERE api_key = '{api_key}' AND human_name='{user.id}'")
            row = pg.cur.fetchone()
            if row:
                scenario_name = row[0]
            else:
                vals = f"bad api key"

    return vals, scenario_name


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

def list_endpoints():
    out = ""

    # https://stackoverflow.com/questions/13317536/get-list-of-all-routes-defined-in-the-flask-app
    def has_no_empty_params(rule):
        defaults = rule.defaults if rule.defaults is not None else ()
        arguments = rule.arguments if rule.arguments is not None else ()
        return len(defaults) >= len(arguments)

    out+="<h4>drdt is serving endpoints:</h4> <ul>"

    for rule in app.app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        if has_no_empty_params(rule):
            url = flask.url_for(rule.endpoint, **(rule.defaults or {}))

            methods = list ( rule.methods )
            for m in ["OPTIONS", "HEAD"]:
                if m in methods:
                    methods.remove(m)

            out += f"<li><a href='{url}'>{rule.endpoint}</a>: {', '.join(methods)}<br/><pre>{app.app.view_functions[rule.endpoint].__doc__}</pre></li><br>"
           # links.append((url, rule.endpoint))

    out +=  "</ul>"

    return out
