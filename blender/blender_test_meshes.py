import shutil

import bpy
import json
import urllib.request


scratch = "/twak/Download/mesh_test"
os.makedirs(scratch, exist_ok=True)

with urllib.request.urlopen("http://dt.twak.org:5000/v0/find-mesh?w=598227.56&n=262624.51&e=598296.11&s=262672.38") as response:
   html = response.read()
   for data in json.loads( urllib.request.urlretrieve() ):
       folder = data[0]
       files = data[1].split(";")
       for file in files:
           shutil.copyfile( f"/home/twak/citnas2/08. Researchers/tom/a14/mesh_chunks/{folder}/{file}", scratch )
           fbx = bpy.ops.import_scene.fbx(filepath=f"{scratch}/{file}")
           # translate fbx


       # load the fbx mesh from mesh_f
