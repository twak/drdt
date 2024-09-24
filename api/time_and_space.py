import json
import traceback
from datetime import datetime, timezone

import flask_login
import shapely
from flask import request

from . import utils


def time_and_scenario_query (table, location = None, scenario = None, cols = [], pg=None, name = "name"):

    if isinstance(location, str):
        return location

    now_utc = datetime.now(timezone.utc) # all is UTC and 27700
    time = request.args.get('time', now_utc.strftime('%Y-%m-%d %H:%M:%S'))
    tn = f"public.{table}"
    user = None if flask_login.current_user.is_anonymous else flask_login.current_user.id

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
            return f" AND ST_Intersects ( {ch}.geom, {utils.envelope(location)} )"

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
