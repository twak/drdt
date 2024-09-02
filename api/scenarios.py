import flask
from flask import Flask, request, redirect
import shapely
import urllib.request
import json
from pathlib import Path
import flask_login
from . import utils
import hashlib
import uuid
import bcrypt
from flask import Response

class User(flask_login.UserMixin):
    pass

def user_loader(username):

    with utils.Postgres() as pg:
        pg.cur.execute( f"SELECT * FROM public.humans WHERE human_name = '{username}';" )
        row = pg.cur.fetchone()
        if row:
            user = User()
            user.id = row["human"]
            user.postgres =  row["postgres"]
            return user

    return

# this one is used which api_key
def request_loader(request):

    api_key = request.args.get('api_key')
    if not api_key:
        return "no api key", 401

    with utils.Postgres() as pg:
        if pg.cur.execute( f"SELECT * FROM public.scenarios WHERE api_key = '{api_key}';" ):
            row = pg.cur.fetchone()
            user = User()
            user.id = row["human"]
            user.scenario = row["scenario"]

            pg.cur.execute( f"SELECT * FROM public.humans WHERE human_name = '{user.id}';" )
            row = pg.cur.fetchone()
            user.postgres =  row["postgres"]

            return user


def all_base_dbs_it():
    for dataset in ["a14"]:
        for table in ["las_chunks", "mesh_chunks", "laso_chunks", "defects_cam", "defects_korec", "os"]:
                yield f"{dataset}_{table}"

def get_hashed_password(plain_text_password):
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    return bcrypt.hashpw(plain_text_password, bcrypt.gensalt())

def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    return bcrypt.checkpw(plain_text_password, hashed_password)

def create_user():

    # if flask_login.current_user.id != 'twak':
    #     return "unauthorized - ask tom (twk22) to create a user!", 401

    if flask.request.method == 'GET':
        return '''
                <form action='create_user' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'/>
                <input type='submit' name='create'/>
               </form>
               '''

    if flask.request.method == 'POST':
        with utils.Postgres(pass_file="pwd_rw.json") as pg:

            pg.cur.execute( "CREATE TABLE IF NOT EXISTS public.humans (human_name text PRIMARY KEY, wordhash text, postgres text);" )

            pg.con.commit()

            username = flask.request.form['username']
            mixin = uuid.uuid4()
            password = hashlib.md5( ("drdt" + mixin.__str__()).encode()).hexdigest()
            db_password = hashlib.md5(password.encode() + mixin.__str__().encode()).hexdigest()

            pg.cur.execute( f"SELECT * FROM public.humans WHERE human_name = '{username}';" )
            if pg.cur.fetchone():
                return f"username {username} already exists in drdt"

            pg.cur.execute( f"SELECT * FROM pg_catalog.pg_user WHERE usename = '{username}';" )
            if pg.cur.fetchone():
                return f"username {username} already exists in postgres"

            hpw = get_hashed_password(password.encode()).__str__().replace("'", "''")
            pg.cur.execute( f"INSERT INTO public.humans VALUES ('{username}', '{hpw}', '{db_password}');" )
            pg.cur.execute( f"CREATE USER {username} WITH PASSWORD '{db_password}';" )

            # read-only on the base dbs
            pg.cur.execute( f"GRANT CONNECT ON DATABASE dt01 TO {username};")
            pg.cur.execute( f"GRANT USAGE ON SCHEMA public TO {username};")
            for db in all_base_dbs_it():
                pg.cur.execute( f"GRANT SELECT ON {db} TO {username};")

            pg.con.commit()

            return f"""<p>done:</p><br/>
            <p>Hi {username}, I have created you an account with password {password} on drdt.</p>
            <p>You also have postgres account with the username {username} and password {db_password}. This gives you read-only access to the base databases.</p>
            <p>You can create scenarios (for writable databases) on <a href="{utils.domain}/list_scenarios">this page</a>.</p>
            """

def login():

    if flask.request.method == 'GET':
        return '''
                <p>Ask tom for a login!</p>
                <form action='login' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'/>
                <input type='password' name='password' id='password' placeholder='password'/>
                <input type='submit' name='submit'/>
               </form>
               '''
    with utils.Postgres() as pg:

        human_name = flask.request.form['username']
        pg.cur.execute( f"SELECT * FROM public.humans WHERE human_name = '{human_name}';" )
        row = pg.cur.fetchone()
        if row:

            if not check_password(flask.request.form['password'], row[1]):
                return Response("Bad Login", status=401, mimetype='application/json')

            user = User()
            user.id = row["human"]
            user.postgres =  row["postgres"]
            flask_login.login_user(user)
            return flask.redirect(flask.url_for('protected'))
        else:
            return Response("Bad Login", status=401, mimetype='application/json')


def list_scenarios():
    page =  f"""
    <body>
    <h1>Protected</h1>
    <p>{flask_login.current_user.id}</p>
    <p>db password: {flask_login.current_user.postgres}</p> 
    """

    with utils.Postgres(pass_file="api/pwd_rw.json") as pg:
        pg.cur.execute( "CREATE TABLE IF NOT EXISTS public.scenarios (scenario text PRIMARY KEY, human_name text, api_key text unique);" )

        page = "<html><body>"

        pg.cur.execute( f"SELECT * FROM public.scenarios WHERE human_name = '{flask_login.current_user.id}';" )
        for row in pg.cur:
            page += f"<p>{row['scenario']} {row['api_key']}"

        page += "</body></html>"

        return page


def logout():
    flask_login.logout_user()
    return 'Logged out'

def unauthorized_handler():
    return 'Unauthorized! <a href="/">login?!</a>', 401

# @app.route("/v0/create_scenario")
# def create_scenario():
#     try:
#         name = request.args['name']
#
#         scenarios = dbz.get_row("scenarios", name)
#         if name in scenarios:
#             return f"scenario {name} already exists"
#
#         dbz.insert_row("scenarios", {"name": name, "created": "now()", "user": username})
#
#         for dataset in ["a14"]:
#             for table in ["las_chunks", "mesh_chunks"]:
#                 dbz.create_table_from(f"{name}_{dataset}_{table}", f"{dataset}_{table}" )
#
#         return "success"
#     except:
#         return "error!"


# ALTER TABLE public."a14_defects_cam"
# ADD existence tsmultirange;
#
# update public."a14_las_chunks" set existence = '{[2021-01-01,]}'
#
# CREATE INDEX a14_las_chunks_geom
#     ON public."a14_las_chunks" USING gist
#     (geom, existence)
#     TABLESPACE pg_default;