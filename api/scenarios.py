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
            user.id = row[0]
            user.postgres =  row[2]
            return user

    return

# this one is used which api_key
def request_loader(request):

    api_key = request.args.get('api_key')
    if not api_key:
        return

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
    # print(bcrypt.hashpw(plain_text_password, bcrypt.gensalt()))
    return bcrypt.hashpw(plain_text_password.encode('utf-8'), bcrypt.gensalt()).decode('utf8')

def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    return bcrypt.checkpw(plain_text_password.encode('utf-8'), hashed_password.encode())

def ensure_humans(pg):
    pg.cur.execute("CREATE TABLE IF NOT EXISTS public.humans (human_name text PRIMARY KEY, wordhash text, postgres text);")

def ensure_scenarios(pg):
    pg.cur.execute("CREATE TABLE IF NOT EXISTS public.scenarios (scenario text PRIMARY KEY, human_name text, api_key text unique);")

def ensure_scenario_tables(pg):
    pg.cur.execute("CREATE TABLE IF NOT EXISTS public.scenario_tables (scenario text, table_name text, api_key text, human_name text);")


def is_admin():
    # return True
    return (not flask_login.current_user.is_anonymous) and flask_login.current_user.id == 'twak'

def create_user():

    if not is_admin():
        return "unauthorized - ask <a href='mailto:twk22@cam.ac.uk'>tom</a> to create a user! (or <a href='/login'>login</a>)", 401

    if flask.request.method == 'GET':
        return '''
                <form action='create_user' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'/>
                <input type='submit' name='create'/>
               </form>
               '''

    if flask.request.method == 'POST':
        with utils.Postgres(pass_file="pwd_rw.json") as pg:

            ensure_humans(pg)

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

            hpw = get_hashed_password(password).__str__().replace("'", "''")
            pg.cur.execute( f"INSERT INTO public.humans VALUES ('{username}', '{hpw}', '{db_password}');" )
            pg.cur.execute( f"CREATE USER {username} WITH PASSWORD '{db_password}';" )

            # read-only on the base dbs
            pg.cur.execute( f"GRANT CONNECT ON DATABASE {utils.table_name} TO {username};")
            pg.cur.execute( f"GRANT USAGE ON SCHEMA public TO {username};")

            # for db in all_base_dbs_it():
            #     try:
            #         pg.cur.execute( f"GRANT SELECT ON {db} TO {username};")
            #
            #         ensure_scenario_tables(pg)
            #         pg.cur.execute(f"INSERT INTO public.scenario_tables VALUES ('{scenario}', '{tn}');")
            #     except:
            #         pass

            pg.con.commit()

            return f"""<p>success:</p><br/>
            <p>Hi, I have created you an account with usernmae/password {username}/{password} on drdt.</p>
            <p>You also have postgres account {username}/{db_password}. This gives you read-only access to the base databases.</p>
            <p>You can create scenarios (for writable databases) on <a href="{utils.domain}/list_scenarios">this page</a>.</p>
            """

def delete_user():
    pass
    # delete tables, scenarios, user
    # REASSIGN OWNED BY twak to postgres;
    # drop owned by twak;
    # drop user twak;


def login():

    if flask.request.method == 'GET':
        return '''
                <h4>login</h4>
                <p>Ask <a href="mailto:twk22@cam.ac.uk">tom<a/> for a login!</p>
                <form action='login' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'/>
                <input type='password' name='password' id='password' placeholder='password'/>
                <input type='submit' name='submit'/>
               </form>
               '''

    if flask.request.method == 'POST':
        # with utils.Postgres(pass_file="pwd_rw.json") as pg:
        #     ensure_humans(pg)

        with utils.Postgres() as pg:

            human_name = flask.request.form['username']
            pg.cur.execute( f"SELECT * FROM public.humans WHERE human_name = '{human_name}';" )
            row = pg.cur.fetchone()
            if row:

                if not check_password(flask.request.form['password'], row[1]):
                    return Response("Bad Login", status=401, mimetype='application/json')

                user = User()
                user.id = row[0]
                user.postgres =  row[2]
                flask_login.login_user(user)
                return flask.redirect(flask.url_for('list_scenarios'))
            else:
                return Response("Bad Login", status=401, mimetype='application/json')

def create_scenario():

    if flask.request.method == 'POST':
        with utils.Postgres(pass_file="pwd_rw.json") as pg:

            ensure_scenarios(pg)

            scenario_name = flask.request.form['scenario_name']

            pg.cur.execute( f"SELECT * FROM public.scenarios WHERE scenario = '{scenario_name}';" )
            if pg.cur.fetchone():
                return f"scenario {scenario_name} already exists"

            api_key = hashlib.md5((uuid.uuid4().__str__()).encode()).hexdigest()

            pg.cur.execute( f"INSERT INTO public.scenarios VALUES ('{scenario_name}', '{flask_login.current_user.id}', '{api_key}');" )

            return flask.redirect(flask.url_for('list_scenarios'))

def list_scenarios():
    page =  f"""
    <body>
    <h1>Protected</h1>
    <p>{flask_login.current_user.id}</p>
    <p>db password: {flask_login.current_user.postgres}</p> 
    """

    with utils.Postgres(pass_file="pwd_rw.json") as pg:
        ensure_scenarios(pg)

    with utils.Postgres() as pg:

        page = "<html><head><title>all scenarios</title></head><body><a href='/logout'>logout</a>"

        page += """ <h4>all scenarios</h4>
            <form action='create_scenario' method='POST'>
                <input type='text' name='scenario_name' id='scenario_name' placeholder='scenario_name'/>
                <input type='submit' name='create'/>
            </form>
            """

        pg.cur.execute( f"SELECT scenario, api_key FROM public.scenarios WHERE human_name = '{flask_login.current_user.id}';" )
        page += f"<p><table border='1'><tr><th>{flask_login.current_user.id}'s scenarios</th><th>api_key</th></tr>"
        for row in pg.cur:
            page += (f"<tr><td>{row[0]}</td><td>"
                     f"<form action='/show_scenario' method='post'><button type='submit' name='scenario_name' value='{row[0]}'>{row[1]}</button></form>"
                     f"</td></tr>")
        page += "</table></p>"

        page += "</body></html>"

        return page


def add_table():

    scenario = flask.request.form['scenario_name']
    api_key = flask.request.form['api_key']
    table_name = flask.request.form['table_name']

    if len(table_name) < 5:
        return "table name too short"

    human = flask_login.current_user.id

    tn = f"__{human}_{scenario}_{table_name}"

    with utils.Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f"SELECT EXISTS ("
           f"SELECT 1 "
           f"FROM pg_tables "
           f"WHERE schemaname = 'public' "
           f"AND tablename = '{tn}' "
        ");")

        if pg.cur.fetchone()[0]:
            return f"table {tn} already exists"

        ensure_scenario_tables(pg)
        pg.cur.execute(f"INSERT INTO public.scenario_tables VALUES ('{scenario}', '{tn}', '{api_key}', '{human}');")

        pg.cur.execute(f"CREATE TABLE IF NOT EXISTS public.{tn} ();")
        pg.cur.execute(f"ALTER TABLE public.{tn} OWNER TO {human};")

    return flask.redirect(flask.url_for('show_scenario', scenario_name=scenario))

def show_scenario():

    if flask.request.method == 'POST':
        scenario = flask.request.form['scenario_name']
    elif flask.request.method == 'GET': # we might forward after add_table etc...
        scenario = flask.request.args.get('scenario_name')

    page = f"<html><head><title>{scenario}</title></head><body><a href='/logout'>logout</a>"

    with utils.Postgres(pass_file="pwd_rw.json") as pg:
        ensure_scenario_tables(pg)

    with utils.Postgres() as pg:
        pg.cur.execute( f"SELECT scenario, api_key, human_name FROM public.scenarios WHERE scenario = '{scenario}' AND human_name = '{flask_login.current_user.id}';" )
        api_key = None
        for row in pg.cur:
            api_key = row[1]
            human_name = row[2]

        if not api_key:
            return f"can't find scenario {scenario}"

        pg.cur.execute( f"SELECT table_name FROM public.scenario_tables WHERE api_key = '{api_key}';" )

        page += (f"<h4>tables for {human_name}'s scenario {scenario}.</h4>"
                 f"<p> api_key {api_key}. postgres password {flask_login.current_user.postgres}.</p>"
                 f"<form action='/delete_scenario' method='post' onsubmit='return confirm(\"Really delete {scenario}?\")'><button type='submit' name='scenario_name' value='{scenario}'>delete</button></form>"
                    f"<form action='add_table' method='POST'>"
                    f"<input type='text' name='table_name' id='table_name' placeholder='new_table_name'/>"
                    f"<input type='hidden' name='scenario_name' value='{scenario}' />"
                    f"<input type='hidden' name='api_key' value='{api_key}' />"
                    f"<input type='submit' name='create'/>"
                    f"</form>"
                 f"<table border='1'><tr><th>table_name</th><th>columns</th></tr>")

        for row in pg.cur:
            table_name = row[0]
            page += f"<tr><td>{table_name}</td><td>"
            with utils.Postgres() as pg2:
                pg2.cur.execute(f"""SELECT *
                                    FROM information_schema.columns
                                    WHERE table_schema = 'public'
                                    AND table_name   = '{table_name}'
                                ;""")
                for row in pg2.cur:
                    page += row[0]+", "
            page += ("</td>"
                        f"<td>"
                     f"<form action='/delete_table' method='post' onsubmit='return confirm(\"Really delete table {table_name}?\")'><button type='submit' name='table_name' value='{table_name}'>delete</button><input type='hidden' name='scenario_name' value='{scenario}' /></form>"
                     "</td></tr>")
        page += "</table>"

    return page

def delete_table():

    scenario = flask.request.form['scenario_name']
    table_name = flask.request.form['table_name']
    human = flask_login.current_user.id

    if not table_name.startswith("__"):
        return f"can't delete {table}"

    with utils.Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f"SELECT table_name FROM public.scenario_tables WHERE table_name = '{table_name}' and human_name = '{human}';")
        if not pg.cur.fetchone():
            return f"can't find table {table_name}"

        pg.cur.execute(f"DROP TABLE {table_name};")
        pg.cur.execute(f"DELETE FROM public.scenario_tables WHERE table_name = '{table_name}' and human_name = '{human}';")

    return flask.redirect(flask.url_for('show_scenario', scenario_name=scenario))


def logout():
    flask_login.logout_user()
    return 'Logged out'

def unauthorized_handler():
    return 'Unauthorized! <a href="/">login?!</a>', 401

# ALTER TABLE public."a14_defects_cam"
# ADD existence tsmultirange;
#
# update public."a14_las_chunks" set existence = '{[2021-01-01,]}'
#
# CREATE INDEX a14_las_chunks_geom
#     ON public."a14_las_chunks" USING gist
#     (geom, existence)
#     TABLESPACE pg_default;