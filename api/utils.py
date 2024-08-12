import json
import psycopg2

sevenseven = 27700
cur, con = None, None

def create_postgres_connection():
    global curs
    with open("api/pwd_rw.json") as fp:
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
