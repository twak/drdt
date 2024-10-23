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
from PIL import Image, ImageEnhance, ImageDraw
from shapely import wkb, wkt
from api import time_and_space

def write_report(ip, i, path):
    if ip.report_path:
        os.makedirs(ip.report_path, exist_ok=True)

    # vertical integral - overlay on OS aerial
    aerial_path = os.path.join(ip.report_path, "aerial.png")

    magma = Image.open(os.path.join(Path(__file__).parent, "magma_orig.png"))
    magma = np.asarray(magma)
    magma = magma[:, :, :3]

    urllib.request.urlretrieve(  # background for vertical image
        f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_aerial&exceptions=application%2Fvnd.ogc.se_inimage&"
        f"SRS=EPSG%3A27700&WIDTH={ip.integral_vert.shape[0]}&HEIGHT={ip.integral_vert.shape[1]}"
        f"&BBOX={path.bounds[0] - ip.vi_pad}%2C{path.bounds[1] - ip.vi_pad}%2C{path.bounds[2] + ip.vi_pad}%2C{path.bounds[3] + ip.vi_pad}",
        aerial_path)

    # vertical integral - overlay on OS aerial
    map_path = os.path.join(ip.report_path, "map.png")

    urllib.request.urlretrieve(  # background for vertical image
        f"http://dt.twak.org:8080/geoserver/ne/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&"
        f"FORMAT=image%2Fpng&TRANSPARENT=true&STYLES&LAYERS=ne%3AA14_OS&exceptions=application%2Fvnd.ogc.se_inimage&"
        f"SRS=EPSG%3A27700&WIDTH={ip.integral_vert.shape[0]}&HEIGHT={ip.integral_vert.shape[1]}"
        f"&BBOX={path.bounds[0] - ip.vi_pad}%2C{path.bounds[1] - ip.vi_pad}%2C{path.bounds[2] + ip.vi_pad}%2C{path.bounds[3] + ip.vi_pad}",
        map_path)

    imA = Image.open(aerial_path)
    imB = Image.open(map_path)

    for p in path.geoms:
        for i in range(len(p.coords) - 1):
            a = p.coords[i]
            b = p.coords[i + 1]
            a = ((a[0] - path.bounds[0] + ip.vi_pad) * ip.vi_scale,
                 imA.height - (a[1] - path.bounds[1] + ip.vi_pad) * ip.vi_scale)
            b = ((b[0] - path.bounds[0] + ip.vi_pad) * ip.vi_scale,
                 imA.height - (b[1] - path.bounds[1] + ip.vi_pad) * ip.vi_scale)
            for im in [imA, imB]:
                ImageDraw.Draw(im).line([a, b], fill=(255, 166, 0), width=5)

    imA.save(aerial_path)
    imB.save(map_path)

    if ip.do_integral_horiz:  # horizontal density integral
        for name, array in [("veg", ip.to_prune_horiz_integral), ("horiz", ip.veg_horiz_integral)]:
            cutoff = max(0.01, np.percentile(array, 99.5))
            r = magma[1][(np.minimum(magma.shape[1] - 1, array * magma.shape[1] / cutoff)).astype(np.int32)]
            r = np.flip(r, axis=0)  # upside down
            im = Image.fromarray(r.astype(np.uint8))

            clo = (ip.v_cut_move + 3) * 10

            imd = ImageDraw.Draw(im, 'RGBA')
            # dim left hand of image
            imd.rectangle( [(0,0), (r.shape[1] // 2 - clo, r.shape[0])], fill=(0,0,0, 200) )

            # draw VTE
            for line in [
                [(r.shape[1] // 2 - clo, 0), (r.shape[1] // 2 - clo, r.shape[0])],
                [(514, r.shape[0]), (610, 0) ] ]:
                imd.line(line, fill=(166, 255, 166), width=2)


            im.save(os.path.join(ip.report_path, f"{name}{'{:02d}'.format(i)}.png"))

    if ip.do_integral_vert:  # vertical density integral
        cutoff = max(ip.integral_vert.max() * 0.75, 1)
        r = 255 - (ip.integral_vert * 255 / cutoff)
        r = r.transpose()
        r = np.flip(r, axis=0)  # upside down
        o = np.zeros((r.shape[0], r.shape[1], 4), dtype=np.uint8)
        o[:, :, 3] = 255 - r  # density = transparency
        o[:, :, :3] = [255, 120, 255]  # purple!
        im = Image.fromarray(o.clip(0, 255))

        bg = Image.open(aerial_path).convert("RGBA")
        bg = ImageEnhance.Brightness(bg).enhance(0.3)
        bg.paste(im, (0, 0), im)
        # override alpha
        bg.putalpha(255)
        bg.save(os.path.join(ip.report_path, f"vert{'{:02d}'.format(i)}.png"))

    if 'Prune' in ip.report_type:
        remove_map = ""
    else:
        remove_map = (f"<h3>Horizontal Removal Map</h3>"
                      f"<br/>Volume to prune: { '%.2f' % ip.pruned_volume} m^3<br>"
                      f"<img src='veg{'{:02d}'.format(i)}.png'>")

    las_link = "<a href='to_prune.las'>Download LAS</a><br/>" if ip.do_make_las_to_prune  else ""

    with open(os.path.join(ip.report_path, "report.html"), "w") as fp:
        fp.write(f"""
        <html><body>
        <h2>Vegetation {ip.report_type} - A14 segment {ip.seg_name}</h2>
        {ip.date}
        <h3>Location</h3>
        <img src="aerial.png">
        <img src="map.png">
        <h3>Horizontal Density</h3>
        {las_link}
        <img src="horiz{'{:02d}'.format(i)}.png">
        {remove_map}
        <h3>Vertical Density</h3>
        <img src="vert{'{:02d}'.format(i)}.png">
        </body></html>
        """)
