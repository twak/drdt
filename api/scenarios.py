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
    pg.cur.execute("CREATE TABLE IF NOT EXISTS public.scenarios (scenario text PRIMARY KEY, human_name text REFERENCES humans, api_key text unique);")

def ensure_scenario_tables(pg):
    pg.cur.execute("CREATE TABLE IF NOT EXISTS public.scenario_tables (scenario text REFERENCES scenarios, table_name text, api_key text, human_name text REFERENCES humans, base text);")
    pg.cur.execute("CREATE SCHEMA IF NOT EXISTS scenario;")


def is_admin():
    # return True
    return (not flask_login.current_user.is_anonymous) and flask_login.current_user.id == 'twak'

def create_user():

    if not is_admin():
        return "unauthorized - ask <a href='mailto:twk22@cam.ac.uk'>tom</a> to create a user! (or <a href='/login'>login</a>)", 401

    if flask.request.method == 'GET':
        out = '''
                <h4>create user</h4>
                <form action='create_user' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'/>
                <input type='submit' name='create' value='create'/>
               </form>
               '''

        with utils.Postgres(pass_file="pwd_rw.json") as pg:
            pg.cur.execute( f"SELECT * FROM public.humans;" )
            out += "<p>existing users:</p><ul>"
            for row in pg.cur:
                out += f"<li>{row[0]}<form action='/delete_user' method='post'><button type='submit' name='human' value='{row[0]}' onsubmit='return confirm(\"Really delete user {row[0]}?\")'>delete</button></form></li>"
            out += "</ul>"

        return out

    if flask.request.method == 'POST':
        with utils.Postgres(pass_file="pwd_rw.json") as pg:

            # ensure_humans(pg)

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

            for db in all_base_dbs_it():
                try:
                    pg.cur.execute( f"GRANT SELECT ON {db} TO {username};")
                    # ensure_scenario_tables(pg)
                    # pg.cur.execute(f"INSERT INTO public.scenario_tables VALUES ('{scenario}', '{tn}');")

                except:
                    pass

            pg.con.commit()

            return f"""<p>success:</p><br/>
            <p>Hi, I have created you an account with usernmae/password {username}/{password} on drdt.</p>
            <p>You also have postgres account {username}/{db_password}. This gives you read-only access to the base databases.</p>
            <p>You can create scenarios (for writable databases) on <a href="{utils.domain}/list_scenarios">this page</a>.</p>
            """

def login():

    if flask_login.current_user.is_authenticated:
        return flask.redirect(flask.url_for('list_scenarios'))

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

            # ensure_scenarios(pg)

            scenario_name = flask.request.form['scenario_name']

            pg.cur.execute( f"SELECT * FROM public.scenarios WHERE scenario = '{scenario_name}';" )
            if pg.cur.fetchone():
                return f"scenario {scenario_name} already exists"

            api_key = hashlib.md5((uuid.uuid4().__str__()).encode()).hexdigest()

            pg.cur.execute( f"INSERT INTO public.scenarios VALUES ('{scenario_name}', '{flask_login.current_user.id}', '{api_key}');" )

            pg.con.commit()

            for table in all_base_dbs_it():
                do_add_table(scenario_name, api_key, table, like=f"public.{table}")

            return flask.redirect(flask.url_for('list_scenarios'))

def list_scenarios():

    human = flask_login.current_user.id

    page =  f"""
            <body>
            """

    # with utils.Postgres(pass_file="pwd_rw.json") as pg:
    #     ensure_scenarios(pg)

    with utils.Postgres() as pg:

        page += (f"<html><head><title>{human}'s scenarios</title></head><body>"
                 f"<h4>{flask_login.current_user.id}</h4><a href='/logout'>logout</a>")
        if is_admin():
            page += (f" | <a href='/create_user'>create user</a>")

            page +=     f"<p>postgres password: {flask_login.current_user.postgres}</p>"


        page += f""" <h4>{human}'s scenarios</h4>
            
            <form action='create_scenario' method='POST'>
                <input type='text' name='scenario_name' id='scenario_name' placeholder='scenario_name'/>
                <input type='submit' name='create' value='create'/>
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

def do_add_table(scenario, api_key, table_name, like=None):
    human = flask_login.current_user.id

    tn = f"{human}_{scenario}_{table_name}"

    with utils.Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f"SELECT EXISTS ("
           f"SELECT 1 "
           f"FROM pg_tables "
           f"WHERE schemaname = 'scenario' "
           f"AND tablename = '{tn}' "
        ");")

        if pg.cur.fetchone()[0]:
            return f"table {tn} already exists"

        ls = f"'{like}'" if like else "NULL"

        # ensure_scenario_tables(pg)
        pg.cur.execute(f"INSERT INTO public.scenario_tables VALUES ('{scenario}', '{tn}', '{api_key}', '{human}', {ls});")

        pg.con.commit()

        sl = f"LIKE {like} INCLUDING ALL" if like else ""

        pg.cur.execute(f"CREATE TABLE IF NOT EXISTS scenario.{tn} ({sl});")
        pg.cur.execute(f"ALTER TABLE scenario.{tn} OWNER TO {human};")

def add_table():

    scenario = flask.request.form['scenario_name']
    api_key = flask.request.form['api_key']
    table_name = flask.request.form['table_name'].strip()

    if len(table_name) < 3:
        return "table name too short"

    do_add_table(scenario, api_key, table_name)

    return flask.redirect(flask.url_for('show_scenario', scenario_name=scenario))

def show_scenario():

    if flask.request.method == 'POST':
        scenario = flask.request.form['scenario_name']
    elif flask.request.method == 'GET': # we might forward after add_table etc...
        scenario = flask.request.args.get('scenario_name')

    page = f"<html><head><title>{scenario}</title></head><body><a href='/logout'>logout</a> | <a href='/list_scenarios'>list scenarios</a>"

    # with utils.Postgres(pass_file="pwd_rw.json") as pg:
    #     ensure_scenario_tables(pg)

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
                 f"<p>api_key {api_key}.</p><p>postgres password {flask_login.current_user.postgres}.</p>"
                 f"<form action='/delete_scenario' method='post' onsubmit='return confirm(\"Really delete scenario {scenario}?\")'><button type='submit' name='scenario_name' value='{scenario}'>delete scenario</button></form>"
                    f"<form action='add_table' method='POST'>"
                    f"<input type='text' name='table_name' id='table_name' placeholder='new_table_name'/>"
                    f"<input type='hidden' name='scenario_name' value='{scenario}' />"
                    f"<input type='hidden' name='api_key' value='{api_key}' />"
                    f"<input type='submit' name='create' value='create'/>"
                    f"</form>"
                 f"<table border='1'><tr><th>table_name</th><th>columns</th></tr>")

        for row in pg.cur:
            table_name = row[0]
            page += f"<tr><td>{table_name}</td><td>"
            with utils.Postgres() as pg2:
                pg2.cur.execute(f"""SELECT *
                                    FROM information_schema.columns
                                    WHERE table_schema = 'scenario'
                                    AND table_name   = '{table_name}'
                                ;""")
                for row in pg2.cur:
                    page += f"{row[3]}, "
            page += ("</td>"
                        f"<td>"
                     f"<form action='/delete_table' method='post' onsubmit='return confirm(\"Really delete table {table_name}?\")'><button type='submit' name='table_name' value='{table_name}'>delete</button><input type='hidden' name='scenario_name' value='{scenario}' /></form>"
                     "</td></tr>")
        page += "</table>"

    return page

def do_delete_table(table_name, human):

    with utils.Postgres(pass_file="pwd_rw.json") as pg:

        pg.cur.execute(f"SELECT table_name FROM public.scenario_tables WHERE table_name = '{table_name}' and human_name = '{human}';")
        if not pg.cur.fetchone():
            return f"can't find table {table_name}"

        try:
            pg.cur.execute(f"DROP TABLE scenario.{table_name};")
        except:
            pass

        with utils.Postgres(pass_file="pwd_rw.json") as pg2:
            try:
                pg2.cur.execute(f"DELETE FROM public.scenario_tables WHERE table_name = '{table_name}' and human_name = '{human}';")
            except:
                pass

def do_delete_scenario(scenario, human):

    with utils.Postgres(pass_file="pwd_rw.json") as pg:
        pg.cur.execute(f"SELECT scenario FROM public.scenarios WHERE scenario = '{scenario}' and human_name = '{human}';")
        if not pg.cur.fetchone():
            return f"can't find scenario {scenario}"

        # delete all tables related to scenario
        pg.cur.execute(f"SELECT table_name,human_name FROM public.scenario_tables WHERE scenario = '{scenario}' and human_name = '{human}';")
        for row in pg.cur:
            do_delete_table(row[0], row[1]) # also deletes the sql tables

        pg.cur.execute(f"DELETE FROM public.scenarios WHERE scenario = '{scenario}' and human_name = '{human}';")

def do_delete_human (human):

    if not is_admin() or human == 'twak':
        return "unauthorized", 401

    with utils.Postgres(pass_file="pwd_rw.json") as pg:
        pg.cur.execute(f"SELECT scenario FROM public.scenario_tables WHERE human_name = '{human}';")
        for row in pg.cur:
            do_delete_scenario(row[0], human)

        pg.cur.execute(f"DELETE FROM public.humans WHERE human_name = '{human}';")
        
        pg.cur.execute(f"REASSIGN OWNED BY {human} TO twak;"
                       f"DROP OWNED BY {human};"
                       f"DROP USER IF EXISTS {human};")

def delete_user():
    human = flask.request.form['human']
    do_delete_human(human)
    return flask.redirect(flask.url_for('create_user'))

def delete_table():

    scenario = flask.request.form['scenario_name']
    table_name = flask.request.form['table_name']
    human = flask_login.current_user.id

    do_delete_table( table_name, human)

    return flask.redirect(flask.url_for('show_scenario', scenario_name=scenario))

def delete_scenario():

    scenario = flask.request.form['scenario_name']
    human = flask_login.current_user.id

    do_delete_scenario( scenario, human)

    return flask.redirect(flask.url_for('list_scenarios'))

def logout():
    flask_login.logout_user()
    return flask.redirect(flask.url_for('/'))

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