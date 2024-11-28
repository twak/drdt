import bpy
from pathlib import Path
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
import utils

workdir = f"{utils.scratch}/fbx_obj"
os.makedirs(workdir, exist_ok=True)

for s in sys.argv[1:]:
    if s.startswith("--input="):
        input = s.split("=")[1].replace('""',"")

# input = "/home/twak/Documents/signs/clean/001.fbx"

output = Path(input).with_suffix(".obj")

bpy.ops.scene.new(type='EMPTY')
bpy.ops.import_scene.fbx(filepath=input)
bpy.ops.wm.obj_export(filepath=str(output), export_materials=False)

bpy.ops.wm.quit_blender()
