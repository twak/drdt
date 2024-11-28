import bpy
import sys
from pathlib import Path
import shutil
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
import utils

for s in sys.argv[1:]:
    if s.startswith("--input="):
        input = s.split("=")[1].replace('""',"")

# input = "/home/twak/Documents/signs/clean/001.fbx"

output = f"{utils.scratch}/mesh.fbx"
bpy.ops.scene.new(type='EMPTY')
bpy.ops.wm.obj_import(filepath=input, forward_axis='X', up_axis='Z')
bpy.ops.export_scene.fbx( filepath=str(output), object_types={'MESH'}, path_mode='COPY', embed_textures=True )
shutil.copyfile(output, Path(input).with_suffix(".fbx"))
bpy.ops.wm.quit_blender()
