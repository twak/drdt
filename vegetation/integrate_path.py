import urllib

import api.utils as utils
from api.utils import Postgres
import shapely
from shapely.geometry import Polygon
import numpy as np
from pathlib import Path
import os
import shutil
import subprocess
import laspy
from PIL import Image, ImageEnhance
from shapely import wkb, wkt
from api import time_and_space

"""
Given a linestring ( a road segment ) we, for each line therin, and compute a wedge shape around it. 
We then download all las files within that wedge, orient them along the line, and add them to a density image.

The output for the road segment is then a vegetation density pointcloud.
"""

veg_horiz_integral = np.zeros((200, 1000))
to_prune_horiz_integral = np.zeros((200, 1000))
integral_vert = None
path = None # path we're working on
vi_scale = 1 # scale of the vertical integral image
vi_pad = 200  # meters expansion beyond path for vertical integral
lases_with_classification = []

# parameters of cut-profile
segment_to_road_edge = 2  # vegetation cut shape... (2 for segment 11; 1.5 for segment 14)
v_cut_move = 1 # move central trim-plane to the "left" away from the verge by this distance
slope = 0.5

def render (path, array):

    resolution = 10 # px per meter

    rw = int(array[0].max() - array[0].min())
    rh = int(array[1].max() - array[1].min())

    array[0] = ((array[0] - array[0].min()) * resolution).clip(0, rw * resolution)
    array[1] = ((array[1] - array[1].min()) * resolution).clip(0, rh * resolution)

    array = array.astype(int)

    r = np.zeros((rw * resolution + 1, rh * resolution + 1))

    for x, y in zip(array[0], array[1]):
        r[rw* resolution - 1- x,y] += 1

    cutoff = np.percentile(r, 95)
    r = 255 - (r * 255 / cutoff).clip(0, 255)

    im = Image.fromarray(r.astype(np.uint8))

    im.save(path)

def do_pdal(name, las_files, workdir):

    with open(os.path.join ( workdir, f"go.json"), "w") as fp:

        fp.write("[\n")
        for f in las_files:
            fp.write(  f'"{f}", \n')

        fp.write(f'''
                {{
                    "type": "filters.merge"
                }},
                {{
                    "type": "writers.las",
                    "filename": "{name}.las"
                }}
                ]
                ''')


    # this requires pdal in the current path (use conda!)
    print("pdaling merging and filtering point clouds...")
    subprocess.run(f'cd {workdir} && pdal pipeline go.json', shell=True, executable='/bin/bash')

def norm(v):
    return v / np.linalg.norm(v)

def perp_vector(a, b):
    v = norm ( np.array([b[0] - a[0], b[1] - a[1]]) )
    return np.array([-v[1], v[0]])

def perp_vector_triple(linestring, i):
# def perp_vector_triple(a, b, c):

    a = linestring[i - 1] if i > 0 else None
    b = linestring[i]
    c = linestring[i + 1] if i < len(linestring) - 1 else None

    if c == None:
        return perp_vector(a, b)
    elif a == None:
        return perp_vector(b, c)
    else:
        v1 = perp_vector(a, b)
        v2 = perp_vector(b, c)
        out = (v1 + v2 )
        out = out / np.linalg.norm(out)
        return out


def process_wedge(eh, start, mid, end, i, ls, sh, seg_name, workdir):

    print(f"now processing wedge {ls}")
    global veg_horiz_integral, to_prune_horiz_integral

    with Postgres() as pg2:

        def loc_query(ch):
            return f" AND ST_DWithin({ch}.geom, ST_SetSRID('{ls.wkb_hex}'::geometry, {utils.sevenseven} ), 10)"

        results = time_and_space.time_and_scenario_query_api("a14_las_chunks", location=loc_query, pg=pg2,
                            api_key="f8c82b4e8156eef1c7a2f24dfd46196a", cols=["type", "geom", "origin", "nas"], time="2026-12-10 00:00:00")

        lases = []

        v1 = np.array([*norm(end - start), 0])
        v2 = [*perp_vector(start, end), 0]
        v3 = np.array([0, 0, 1])

        # rotate cloud to lie along y axes
        rotate = np.array([[v2[0], v1[0], v3[0], 0],
                           [v2[1], v1[1], v3[1], 0],
                           [v2[2], v1[2], v3[2], 0],
                           [0, 0, 0, 1]])

        length = np.linalg.norm(end - start)

        for b in results:

            chunk_name = b["name"]
            chunk_nas = b["nas"]

            print("processing las chunk", chunk_name)
            dest = os.path.join(workdir, chunk_name)

            if not os.path.exists(dest):
                print(f"  downloading {chunk_name}...")
                shutil.copy(utils.nas_mount+chunk_nas, dest)

            with laspy.open(dest) as fh:
                lasdata = fh.read()

                xyz = np.stack((
                    lasdata.X * lasdata.header.x_scale - mid[0],  # move x, y to origin
                    lasdata.Y * lasdata.header.y_scale - mid[1],
                    lasdata.Z * lasdata.header.z_scale,  # height is moved to origin below
                    np.zeros((lasdata.xyz.shape[0])),  # we'll use this as padding for 4x4 rotation
                    lasdata.classification.array,  # we'll use this for filtering out vegetation
                    np.arange(lasdata.xyz.shape[0])  # index
                ), axis=1)

                # filter out points outside the wedge before any other transforms
                l2 = length / 2
                for plane in [[*v1, l2], [*(-v1), l2]]:
                    xyz = xyz[(xyz[:, 0] * plane[0] + xyz[:, 1] * plane[1] + xyz[:, 2] * plane[2] + plane[3]) > 0]

                xyz[:, :4] = np.matmul(xyz[:, :4], rotate)  # rotation
                xyz[:, 2] -= sh + (eh - sh) * (xyz[:, 1] + length / 2) / length  # linearly interpolate height of the length of the segment (shear transform)

                pruned_filename = f"pruned_{chunk_name[:-4]}_chunks_{seg_name}_{i}.las"

                if False:  # create pruned las chunks, remove old at time
                    create_pruned_pc(chunk_name, chunk_geom, chunk_origin, lasdata, pruned_filename, xyz)

                if True:
                    create_pc_with_prune_class(lasdata, pruned_filename, xyz)

                if True:  # integrate down whole segment
                    integrate_horiz(xyz, mid)


def integrate_horiz(xyz, mid):

    global veg_horiz_integral, to_prune_horiz_integral, integral_vert, path

    xyz = xyz[(xyz[:, 4] == 3) | (xyz[:, 4] == 4) | (xyz[:, 4] == 5)]  # vegetation filter
    veg_horiz_integral += \
        np.histogram2d(xyz[:, 2], xyz[:, 0], bins=(200, 1000), range=[[-1, 19], [-50, 50]], density=False)[0]

    veg_togo = xyz[
        (xyz[:, 0] + v_cut_move > 0) &  # vertical plane in center of road
        ((xyz[:, 0] - segment_to_road_edge) < slope * xyz[:, 2])]  # sloped line at 'edge' of road.
    to_prune_horiz_integral += \
    np.histogram2d(veg_togo[:, 2], veg_togo[:, 0], bins=(200, 1000), range=[[-1, 19], [-50, 50]], density=False)[0]


def create_pc_with_prune_class(lasdata, pruned_filename, xyz, do_write=True):
    # write point cloud with pruned classification
    global veg_horiz_integral, to_prune_horiz_integral, lases_with_classification, integral_vert, path, vi_pad, v_cut_move
    lases_with_classification.append(f"{pruned_filename}.las")


    to_keep = xyz[:, 5].astype(int)  # remove before start, end planes on segment (but keep pruned!)
    to_remove = xyz[
        ((xyz[:, 4] == 3) | (xyz[:, 4] == 4) | (xyz[:, 4] == 5)) &
         (xyz[:, 0] + v_cut_move> 0) &
        ((xyz[:, 0] - segment_to_road_edge) < slope * xyz[:, 2])]

    # for each index still in to_remove, set classification in laspy to 13
    lasdata.classification[to_remove[:, 5].astype(int)] = 13

    if do_write:
        location = f"{utils.nas_mount_w}{utils.a14_root}vege_pruned_las/"
        file = utils.unique_file(location, pruned_filename)
        with laspy.open(file, mode="w", header=lasdata.header) as writer:
            writer.write_points(lasdata.points[to_keep])

    # overhead view of the pruned vegetation
    vert_data = lasdata.xyz[to_remove[:, 5].astype(int)]
    integral_vert += np.histogram2d( vert_data[:, 0], vert_data[:, 1], bins=(integral_vert.shape[0], integral_vert.shape[1]), range=[[path.bounds[0] - vi_pad, path.bounds[2]+ vi_pad], [path.bounds[1]- vi_pad, path.bounds[3]+ vi_pad]], density=False)[0]


def create_pruned_pc(chunk_name, chunk_geom, chunk_origin, lasdata, pruned_filename, xyz, date = "2024-10-02 00:12:34"):

    # a cloud without the pruned vegetation
    global veg_horiz_integral, to_prune_horiz_integral, v_cut_move
    pruned = xyz[((xyz[:, 4] != 3) & (xyz[:, 4] != 4) & (xyz[:, 4] != 5)) |  # not vegetation, or
                  (xyz[:, 0] + v_cut_move < 0) |  # before vertical plane in center of road
                 ((xyz[:, 0] - segment_to_road_edge) > slope * xyz[:, 2])]  # after sloped line at 'edge' of road.

    if len (pruned) == len (xyz):
        print("no vegetation pruned!")
        return

    # take remaining indicies; apply as filter to original lasdata; write back as new las file
    with laspy.open(os.path.join(utils.nas_mount_w + utils.a14_root, "vege_pruned_las",
                                 f"{pruned_filename}"), mode="w", header=lasdata.header) as writer:
        to_keep = pruned[:, 5].astype(int)
        writer.write_points(lasdata.points[to_keep])

    with Postgres(pass_file="fred.json") as pg:

        orig_nas_path = utils.las_route +"/" + chunk_name

        print(f"inserting into db {pruned_filename}")

        # remove any existing pruned point cloud - create new entry with existence range setup (if not already removed by previous query)
        pg.cur.execute(
            f"INSERT INTO scenario.fred_vege_a14_las_chunks (geom, type, name, nas, origin, existence) "
            f"SELECT {utils.post_geom(chunk_geom)}, 'point_cloud', '{chunk_name}', '{orig_nas_path}', {utils.post_geom(chunk_origin)}, '{{[,{date}]}}' "
            f"WHERE NOT EXISTS (SELECT name FROM scenario.fred_vege_a14_las_chunks WHERE name = '{chunk_name}' );" )

        # add trimmed point cloud to the scenario database
        pg.cur.execute(
            f"INSERT INTO scenario.fred_vege_a14_las_chunks(geom, type, name, nas, origin, existence) "
            f"VALUES ({utils.post_geom(chunk_geom)}, 'point_cloud', '{pruned_filename}', '{utils.a14_root}vege_pruned_las/{pruned_filename}', "
            f"{utils.post_geom(chunk_origin)}, '{{[{date},]}}' )" )


def integrate_path(seg_name):

    print("Integrating path: ", seg_name)

    # workdir = Path("/home/twak/Downloads/geojsons")
    workdir = Path("/home/twak/Downloads/las_cache")

    global veg_horiz_integral, to_prune_horiz_integral, integral_vert
    # the output image. we add to it for each segment of the line (and wedge to lidar)

    # vertical integral - overlay on OS aerial
    background_path = os.path.join("/home/twak/Downloads/aerial.png")

    # with Postgres(pass_file="pwd_rw.json") as pg:
    #     pg.cur.execute(f'DROP TABLE IF EXISTS public.a14_pruned_las_chunks')
    #     pg.cur.execute("""
    #     CREATE TABLE IF NOT EXISTS public.a14_pruned_las_chunks
    #     (
    #         geom geometry,
    #         type text COLLATE pg_catalog."default",
    #         name text COLLATE pg_catalog."default" NOT NULL,
    #         nas text COLLATE pg_catalog."default",
    #         origin geometry(Point,27700),
    #         existence tsmultirange,
    #         CONSTRAINT a14_pruned_las_chunks_pkey PRIMARY KEY (name)
    #     )
    #     """)

    magma = Image.open(os.path.join(Path(__file__).parent, "magma_orig.png"))
    magma = np.asarray(magma)
    magma = magma[:, :, :3]

    with (Postgres() as pg):
        pg.cur.execute(f"""
            SELECT  id, ST_AsText(geom), geom_z,  'Section_La', 'Section_St', 'Section_En', 'Length', 'Start_Date', 'End_Date', 'Section_Fu', 'Road_Numbe', 'Road_Name', 'Road_Class', 'Single_or_'               
            FROM public.a14_segments WHERE id = '{seg_name}' 
            """ )

        results = pg.cur.fetchone()
        if results[3] == None:
            print("No height info for this segment! run sample_height...")
            return

        global integral_vert, vi_scale, vi_pad, path

        path = shapely.from_wkt(results[1])
        path_z = shapely.from_wkb(results[2])

        print(path)

        # create a blank image for the vertical integral
        integral_vert = np.zeros(( int ( (path.bounds[2] - path.bounds[0] + 2*vi_pad ) * vi_scale), int ( ( path.bounds[3] - path.bounds[1] + 2 * vi_pad ) * vi_scale ) ) )

        urllib.request.urlretrieve( # background for vertical image
            f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
            f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_aerial&exceptions=application%2Fvnd.ogc.se_inimage&"
            f"SRS=EPSG%3A27700&WIDTH={integral_vert.shape[0]}&HEIGHT={integral_vert.shape[1]}"
            f"&BBOX={path.bounds[0] - vi_pad}%2C{path.bounds[1] - vi_pad}%2C{path.bounds[2] + vi_pad}%2C{path.bounds[3] + vi_pad}",
            background_path)

        for lsi, linestring in enumerate(path.geoms):

            extent = 100 # how far does the wedge extend from the segment

            # for each line segment, create an envelope. we expect a single linestring per geometry.
            for i in range (len(linestring.coords)-1):

                print (f"processing segment {i} of {len(linestring.coords)-1}")

                name = seg_name+str(i)

                start =  np.array(linestring.coords[i])
                end =  np.array(linestring.coords[i+1])
                sh = path_z.coords[i][2]
                eh = path_z.coords[i+1][2]

                mid = (start + end) / 2

                perp_start = perp_vector_triple(linestring.coords, i) * extent
                perp_end = perp_vector_triple(linestring.coords, i+1) * extent

                a = start + perp_start
                b = end + perp_end
                c = end - perp_end
                d = start - perp_start
                boundary = [ a, b, c ,d ]
                ls = Polygon(boundary)

                process_wedge(eh, start, mid, end, i, ls, sh, seg_name, workdir)


            # horizontal density integral
            for name, array in [("veg", to_prune_horiz_integral), ("horiz", veg_horiz_integral)]:
                cutoff = max(0.01,np.percentile(array, 99.5))
                r = magma[1][(np.minimum(magma.shape[1] - 1, array * magma.shape[1] / cutoff)).astype(np.int32)]

                r=np.flip ( r, axis=0 ) # upside down
                im = Image.fromarray(r.astype(np.uint8))
                im.save( os.path.join("/home/twak/Downloads", f"{name}{'{:02d}'.format(i)}.png") )

            # vertical density integral
            cutoff = max ( integral_vert.max() * 0.75, 1)
            r = 255 - (integral_vert * 255 / cutoff)
            r = r.transpose()
            r = np.flip(r, axis=0)  # upside down
            o = np.zeros((r.shape[0], r.shape[1], 4), dtype=np.uint8)
            o[:, :, 3] = 255-r # density = transparency
            o[:, :, :3] = [255, 120, 255] # purple!
            im = Image.fromarray(o.clip(0, 255))

            bg = Image.open(background_path).convert("RGBA")
            bg = ImageEnhance.Brightness(bg).enhance(0.3)
            bg.paste(im, (0, 0), im)
            # override alpha
            bg.putalpha(255)
            bg.save(os.path.join("/home/twak/Downloads", f"vert{'{:02d}'.format(i)}.png"))

if __name__ == '__main__':
    integrate_path("11")
    # integrate_path("14")