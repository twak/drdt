import flask
from flask import Flask, request, redirect
import shapely
import urllib.request
import json
from pathlib import Path
import flask_login
from . import utils

users = {'foo@bar.tld': {'password': 'secret'}}

class User(flask_login.UserMixin):
    pass

def user_loader(email):
    if email not in users:
        return

    user = User()
    user.id = email
    return user


def request_loader(request):
    email = request.form.get('email')
    if email not in users:
        return

    user = User()
    user.id = email
    return user

def login():

    if flask.request.method == 'GET':
        return '''
               <form action='login' method='POST'>
                <input type='text' name='email' id='email' placeholder='email'/>
                <input type='password' name='password' id='password' placeholder='password'/>
                <input type='submit' name='submit'/>
               </form>
               '''

    with utils.Postgres(pass_file="api/pwd_rw.json") as pg:

        pg.cur.execute( "CREATE TABLE IF NOT EXISTS public.humans (i integer);" )


    email = flask.request.form['email']
    if email in users and flask.request.form['password'] == users[email]['password']:
        user = User()
        user.id = email
        flask_login.login_user(user)
        return flask.redirect(flask.url_for('protected'))

    return 'Bad login'


def protected():
    return 'Logged in as: ' + flask_login.current_user.id

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