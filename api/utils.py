import json
import psycopg2

sevenseven = 27700
cur, con = None, None

las_route = "/08. Researchers/tom/a14/las_chunks"
las_route = "/08. Researchers/tom/a14/mesh_chunks"
nas_mount = f"/home/twak/citnas"
api_url = "http://dt.twak.org:5000/"

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
