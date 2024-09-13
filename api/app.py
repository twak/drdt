import traceback

import flask
from flask import Flask, request, redirect
import shapely
import urllib.request
import json
from pathlib import Path
import flask_login
from . import utils, scenarios
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = Path('api/flask_secret_key').read_text()
app.debug = True
login_manager = flask_login.LoginManager()
login_manager.init_app(app)

@app.route('/')
def index():

    if flask_login.current_user.is_authenticated:
        return flask.redirect(flask.url_for('list_scenarios'))

    # https://stackoverflow.com/questions/13317536/get-list-of-all-routes-defined-in-the-flask-app
    def has_no_empty_params(rule):
        defaults = rule.defaults if rule.defaults is not None else ()
        arguments = rule.arguments if rule.arguments is not None else ()
        return len(defaults) >= len(arguments)

    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        if has_no_empty_params(rule):
            url = flask.url_for(rule.endpoint, **(rule.defaults or {}))

            methods = list ( rule.methods )
            for m in ["OPTIONS", "HEAD"]:
                if m in methods:
                    methods.remove(m)

            links.append(f"<a href='{url}'>{rule.endpoint}</a>: {', '.join(methods)}")
            # links.append((url, rule.endpoint))

    out = ("<html><head><title>drdt</title></head><body><h4>i am drdt; a digital twin</h4>"
          "<p>would you like to <a href='/login'>login</a>?</p>"
        "<p>serving endpoints:</p> <ul>")

    for link in links:
        out += f"<li>{link}</li><br>"

    out +=  "</ul></body></html>"

    return out


def envelope(vals):
    return (f"ST_MakeEnvelope({vals['w']}, {vals['s']}, {vals['e']}, {vals['n']}, 27700 )::geometry('POLYGON')")

# def scenario_union(scenario_name, table_name):
#     with utils.Postgres() as pg:
#
#         pg.execute(
#             f"SELECT name, existence FROM "
#             f"public.{table_name}"
#             f"INTERSECT"
#             f"SELECT name, existence FROM "
#             f"scenario.{scenario_name}_{table_name}" )

"""
    this query returns the requested values from the requested time
    across the base and scenario tables. It computes the union (*) of the times on the intersection,
    and then combines (union) with the remainder 
    
    cols are the additional columns to return
    
    return a list of dictionaries per query result
"""

def time_and_scenario_query (table, location = None, scenario = None, cols = [], pg=None, name = "name"):

    now_utc = datetime.now(timezone.utc) # all is UTC and 27700
    time = request.args.get('time', now_utc.strftime('%Y-%m-%d %H:%M:%S'))
    tn = f"public.{table}"
    user = flask_login.current_user.id

    cols_to_decode = []

    geom_names = ["origin", "geom", "buffer"]

    for i in range(len(cols)):
        for s in geom_names:
            if cols[i] == s:
                cols_to_decode.append(i)

    def col_str(ch):

        nonlocal cols, geom_names
        if len(cols) == 0:
            return ""

        out = ""
        for i in range(len(cols)):
            s = cols[i]
            if s in geom_names:
                out += f", ST_AsText({ch}.{s})"
            else:
                out += f", {ch}.{s}"

        return out

    def loc_str(ch):
        if location is None:
            return ""
        else:
            return f" AND ST_Intersects ( {ch}.geom, {envelope(location)} )"

    if scenario is None:
        q = f"""
            SELECT d.{name} n2, d.existence e2{col_str('d')}
                FROM {tn} d
                WHERE d.existence @> '{time}'::timestamp {loc_str('d')}
        """
    elif user is not None:

        sn = f"scenario.{user}_{scenario}_{table}"

        q = f""" 
                --- when I wrote the below God and I knew what I was thinking...
                SELECT x.{name}, x.existence * y.existence as existence{col_str('x')}
                    FROM {sn} x JOIN {tn} y on y.{name} = x.{name}
                    WHERE x.existence * y.existence @> '{time}'::timestamp {loc_str('x')}
                UNION
                    (SELECT a.{name} n2, a.existence e2{col_str('a')}
                        FROM {sn} a
                        WHERE a.existence @> '{time}'::timestamp {loc_str('a')} AND
                        NOT EXISTS (SELECT 1 from {tn} b where a.{name} = b.{name}))
                UNION
                    (SELECT d.{name} n2, d.existence e2{col_str('d')}
                        FROM {tn} d
                        WHERE d.existence @> '{time}'::timestamp {loc_str('d')} AND
                        NOT EXISTS (SELECT 1 from {sn} e where d.{name} = e.{name}))
        """
    else:
        print(traceback.format_exc())
        return "pass user and scenario together!"

    if pg is None:
        with utils.Postgres() as pg:
            pg.cur.execute(q)
    else:
        pg.cur.execute(q)

    out = []
    for res in pg.cur.fetchall():
        # pt = shapely.from_wkt(x[1])
        outi = {}
        out.append(outi)
        outi[name] = res[0]
        outi['existence'] = res[1]

        for i in range(2, len(cols)+2):
            outi[cols[i-2]] = res[i]
            if i-2 in cols_to_decode:
                outi[cols[i-2]] = shapely.from_wkt(outi[cols[i-2]])

    return out


def find_lasx(table, with_origin=False):

    vals, scenario_name = utils.build_commond_state()

    cols = ['origin'] if with_origin else []

    with utils.Postgres() as pg:
        results = time_and_scenario_query(table, location=vals, scenario=scenario_name, cols=cols, pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        if with_origin:
            pt = x['origin']
            out.append((x['name'], pt.x, pt.y))
        else:
            out.append(x['name'])

    return json.dumps(out)


"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/las_chunks

    for example, with the coords (epsg:27700)

    /v0/find-las?w=601158.9&n=261757.9&e=601205.6&s=261660.2

"""
@app.route("/v0/find-las")
def find_las():

    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_las_chunks", location=vals, scenario=scenario_name, pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        out.append(x['name'])

    return json.dumps(out)

"""
    similarly for /v0/find-las, except the reply includes the x and y offset in 27700
    also 50m lower, and each point cloud is at the origin
"""

@app.route("/v0/find-laso")
def find_laso():

    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_laso_chunks", location=vals, scenario=scenario_name, cols=['origin'], pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        pt = x['origin']
        out.append([x['name'], pt.x, pt.y])

    return json.dumps(out)

"""
    returns a list of nas-las files which can be found on the nas in the folder:
        /08. Researchers/tom/a14/mesh_chunks

    for example, with the coords (epsg:27700)

    /v0/find-mesh?w=598227.56&n=262624.51&e=598296.11&s=262672.38

    returns a list of pairs - the first of which is the folder_name, the second is semi-colon delimetered list of files in the folder which make up the mesh:

    [["w_598260.0_262620.0", 598260.0, 262620.0, "w_598260.0_262620.0_pavement.jpg;w_598260.0_262620.0_mesh.fbx"], ["w_598270.0_262620.0", 598270.0, 262620.0, "w_598270.0_262620.0_mesh.fbx;w_598270.0_262620.0_pavement.jpg"], ...]
    
    In this output, the first mesh is made up of the files:
    
    /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_mesh.fbx
    /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_pavement.jpg
    
    with offset 598260.0, 262620.0
"""

def find_mesh_x(table, extra_columns=None):
    vals = utils.get_nsew()

    if isinstance(vals, str):
        return vals, 500

    with utils.Postgres() as pg:

        ec = ""
        if extra_columns:
            ec = ", " + ", ".join(extra_columns)

        pg.cur.execute(
            f"""
                SELECT  name, files, ST_AsText(origin) {ec}
                FROM public."{table}"
                WHERE ST_Intersects
                ( geom, {envelope(vals)} )
                """)

        out = []
        for x in pg.cur.fetchall():
            if x[0] is None:
                continue # not all potholes have meshes
            pt = shapely.from_wkt(x[2])
            out.append((x[0], pt.x, pt.y, x[1]))

        return json.dumps(out)

    return "failed to connect to database", 500

@app.route("/v0/find-mesh")
def find_mesh():

    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_mesh_chunks", location=vals, scenario=scenario_name, cols=['origin', 'files'], pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        pt = x['origin']
        out.append((x['name'], pt.x, pt.y, x['files']))

    return json.dumps(out)

    return find_mesh_x("a14_mesh_chunks")


"""
    similar to find_mesh, but for defects. 
    meshes are in : /citnas/08. Researchers/tom/a14/mesh_defects
"""
@app.route("/v0/find-defect-meshes")
def find_defect():

    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_mesh_chunks", location=vals, scenario=scenario_name, cols=['origin', 'files', 'gpr_nas'], pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        pt = x['origin']
        out.append((x['name'], pt.x, pt.y, x['files']))

    return json.dumps(out)

"""
    returns a section of the orthomosaic at resolution width x height for given 27700 area
     
    /v0/pavement?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
"""

@app.route("/v0/pavement")
def find_pavement():

    vals = utils.get_nsew(opt={"scale":1})
    if isinstance(vals, str):
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float (vals['n']) - float(vals['s'])) * float(vals['scale'])
    width  = (float(vals['e']) - float(vals['w'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_pavement_orthomosaics&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['w']}%2C{vals['s']}%2C{vals['e']}%2C{vals['n']}", code=302)


"""
    returns a section of the os aerial image at resolution width x height for given 27700 area

    /v0/aerial?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
"""

@app.route("/v0/aerial")
def find_aerial():

    vals = utils.get_nsew(opt={"scale":10})
    if isinstance(vals, str)  :
        return vals # error
    for k in vals.keys():
        print(f"{k} {vals[k]}")

    height = (float(vals['n']) - float(vals['s'])) * float(vals['scale'])
    width = (float(vals['e']) - float(vals['w'])) * float(vals['scale'])

    return redirect(f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
                        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_aerial&exceptions=application%2Fvnd.ogc.se_inimage&"
                        f"SRS=EPSG%3A27700&WIDTH={int(width)}&HEIGHT={int(height)}"
                        f"&BBOX={vals['w']}%2C{vals['s']}%2C{vals['e']}%2C{vals['n']}", code=302)


# **************************************** login & scenarios ****************************************

@login_manager.user_loader
def user_loader(username):
    return scenarios.user_loader(username)

# this one is used for api_keys
@login_manager.request_loader
def request_loader(request):
    return scenarios.request_loader(request)

@app.route('/login', methods=['GET', 'POST'])
def login():
    return scenarios.login()

@app.route('/logout')
def logout():
    flask_login.logout_user()
    return 'Logged out'

@app.route('/list_scenarios')
@flask_login.login_required
def list_scenarios():
    return scenarios.list_scenarios() # 'Logged in as: ' + flask_login.current_user.id

@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized! <a href="/">login?!</a>', 401

@app.route ('/create_user', methods=['GET', 'POST'])
@flask_login.login_required
def create_user():
    return scenarios.create_user()

@app.route ('/delete_user', methods=['POST'])
@flask_login.login_required
def delete_user():
    return scenarios.delete_user()

@app.route ('/create_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def create_scenario():
    return scenarios.create_scenario()

@app.route ('/show_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def show_scenario():
    return scenarios.show_scenario()

@app.route ('/delete_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def delete_scenario():
    return scenarios.delete_scenario()

@app.route ('/add_table', methods=['GET', 'POST'])
@flask_login.login_required
def add_table():
    return scenarios.add_table()

@app.route ('/delete_table', methods=['GET', 'POST'])
@flask_login.login_required
def delete_table():
    return scenarios.delete_table()
