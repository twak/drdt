def create_postgres_connection():
    global curs
    with open("api/pwd.json") as fp:
        pwp = json.load(fp)
    conn = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
    curs = conn.cursor()
    return curs

def ro_create_postgres_connection():
    global curs
    with open("api/ro_pwd.json") as fp:
        pwp = json.load(fp)
    conn = psycopg2.connect(dbname=pwp['dbname'], user=pwp['user'], password=pwp['password'], host=pwp['host'])
    curs = conn.cursor()
    return curs
