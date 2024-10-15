import flask
from flask import Flask, redirect
import json
from pathlib import Path
import flask_login
from . import utils, scenarios, defects
from shapely import wkb

from .time_and_space import time_and_scenario_query, find_mesh_x

app = Flask(__name__)
app.secret_key = Path('api/flask_secret_key').read_text()
app.debug = True
login_manager = flask_login.LoginManager()
login_manager.init_app(app)

from flask import request

@app.route('/')
def index():
    """
        Index
    """
    if flask_login.current_user.is_authenticated:
        return flask.redirect(flask.url_for('list_scenarios'))

    out = ("<html><head><title>drdt</title></head><body><h4>i am drdt; a digital twin</h4>"
          "<p>would you like to <a href='/login'>login</a>?</p>")

    out += scenarios.list_endpoints()

    out +=  "</body></html>"

    return out



@app.route("/v0/find-las")
def find_las():
    """
        returns a list of nas-las files which can be found on the nas in the folder:
            /08. Researchers/tom/a14/las_chunks

        for example, with the coords (epsg:27700)

        /v0/find-las?w=601158.9&n=261757.9&e=601205.6&s=261660.2

    """
    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_las_chunks", location=vals, scenario=scenario_name, pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        out.append(x['name'])

    return json.dumps(out)



@app.route("/v0/find-laso")
def find_laso():
    """
        similarly for /v0/find-las, except the reply includes the x and y offset in 27700
        also 50m lower, and each point cloud is at the origin
    """
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

@app.route("/v0/find-gpr")
def find_gpr():
    """
        returns a list of nas-las files and offset which can be found on the nas in the folder:
            /08. Researchers/tom/a14/gpr_chunks

        for example, with the coords (epsg:27700)
        /v0/find-gpr?w=601158.9&n=261757.9&e=601205.6&s=261660.2

        it might return

        [["w_601200.0_261730.0.las", 601200.0, 261730.0], ... ]

        where w_601200.0_261730.0.las is the file to be displayed at the offset 601200.0, 261730.0

    """
    vals, scenario_name = utils.build_commond_state()

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_gpr_chunks", location=vals, scenario=scenario_name, cols=['origin'], pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        pt = x['origin']
        out.append([x['name'], pt.x, pt.y])

    return json.dumps(out)

@app.route("/v0/find-mesh")
def find_mesh():
    """
        returns a list of nas-las files which can be found on the nas in the folder:
            /08. Researchers/tom/a14/mesh_chunks

        for example, with the coords (epsg:27700) and collecting the 10 x 10m chunks: (

        /v0/find-mesh?w=598227.56&n=262624.51&e=598296.11&s=262672.38

        returns a list of pairs - the first of which is the folder_name, the second is semi-colon delimetered list of files in the folder which make up the mesh, and the nas location in which to find the folder:

        [["w_598260.0_262620.0", 598260.0, 262620.0, "w_598260.0_262620.0_pavement.jpg;w_598260.0_262620.0_mesh.fbx"], ["w_598270.0_262620.0", 598270.0, 262620.0, "w_598270.0_262620.0_mesh.fbx;w_598270.0_262620.0_pavement.jpg", "/08. Researchers/tom/a14/mesh_chunks_50/w_598250.0_262650.0"], ...]

        In this output, the first mesh is made up of the files:

        /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_mesh.fbx
        /08. Researchers/tom/a14/mesh_chunks/w_598260.0_262620.0/w_598260.0_262620.0_pavement.jpg

        with offset 598260.0, 262620.0

        You can optionally include a scale (currently 10 (default) or 50 meters) to change the size of the chunks returned:
        /v0/find-mesh?w=598227.56&n=262624.51&e=598296.11&s=262672.38&scale=50

        These meshes are created using pts_to_mesh.py.
    """

    vals, scenario_name = utils.build_commond_state()
    scale = 10
    if 'scale' in request.args:
        scale = int(request.args.get('scale'))

    if scale not in [10, 50]:
        return f"uknown scale {scale} - currently we have 10 and 50m chunks"

    def loc(ch):
        return f" AND ST_Intersects ( {ch}.geom, {utils.envelope(vals)} ) AND chunk_size = {scale}"

    with utils.Postgres() as pg:
        results = time_and_scenario_query("a14_mesh_chunks", location=loc, scenario=scenario_name, cols=['origin', 'files', 'nas'], pg=pg)

    if isinstance(results, str):
        return results, 500

    out = []
    for x in results:
        pt = x['origin']
        out.append((x['name'], pt.x, pt.y, x['files'], x['nas']))


    return json.dumps(out)

@app.route("/v0/find-defect-meshes")
def find_defect():
    """
        similar to find_mesh, but for defects.
        meshes are in : /citnas/08. Researchers/tom/a14/mesh_defects
    """
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



@app.route("/v0/pavement")
def find_pavement():
    """
        returns a section of the orthomosaic at resolution width x height for given 27700 area

        /v0/pavement?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
    """
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



@app.route("/v0/aerial")
def find_aerial():
    """
        returns a section of the os aerial image at resolution width x height for given 27700 area

        /v0/aerial?w=601158.9&n=261757.9&e=601205.6&s=261660.2&scale=10
    """
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


@app.route("/v0/request_site")
def request_site():
    """
        The AMP uses this to request the next site to visit. This method is a demo and does not yet use scenarios.

        Returns id, type, area (m2), and wkt in 27700 of the largest crack in the database.

        e.g. [228, "crack_longitudinal", 4.236841869066629, "MULTIPOLYGON ..."]
    """
    return defects.request_site()

@app.route("/v0/show_cracks")
def show_cracks():
    """
        html formatted list of all cracks in the dataset by area.
    """
    return defects.show_cracks()


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
    """
        flask user login
    """
    return scenarios.login()

@app.route('/logout')
def logout():
    """
        flask user logout
    """
    flask_login.logout_user()
    return 'Logged out'

@app.route('/list_scenarios')
@flask_login.login_required
def list_scenarios():
    """
        Displays a list of scenarios for logged in users.
    """
    return scenarios.list_scenarios() # 'Logged in as: ' + flask_login.current_user.id

@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized! <a href="/">login?!</a>', 401

@app.route ('/create_user', methods=['GET', 'POST'])
@flask_login.login_required
def create_user():
    """
        (admin only) allows the creation of a user. Interface with this via the web interface.
    """
    return scenarios.create_user()

@app.route ('/delete_user', methods=['POST'])
@flask_login.login_required
def delete_user():
    """
        (admin only) deletes a user. Interface with this via the web interface.
    """
    return scenarios.delete_user()

@app.route ('/create_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def create_scenario():
    """
        creates a new scenario. Interface with this via the web interface.
    """
    return scenarios.create_scenario()

@app.route ('/show_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def show_scenario():
    """
        shows tables and keys for a scenario. Interface with this via the web interface.
    """
    return scenarios.show_scenario()

@app.route ('/delete_scenario', methods=['GET', 'POST'])
@flask_login.login_required
def delete_scenario():
    """
        deletes a scenario. Interface with this via the web interface.
    """
    return scenarios.delete_scenario()

@app.route ('/add_table', methods=['GET', 'POST'])
@flask_login.login_required
def add_table():
    """
        adds a table to a scenario. Interface with this via the web interface.
    """
    return scenarios.add_table()

@app.route ('/delete_table', methods=['GET', 'POST'])
@flask_login.login_required
def delete_table():
    """
        removes a table to a scenario. Interface with this via the web interface.
    """
    return scenarios.delete_table()

