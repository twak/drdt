import shutil
import bpy
import json
import urllib.request
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
import utils


scratch = f"{utils.scratch}/mesh_test"
os.makedirs(scratch, exist_ok=True)

global runs    
runs = 0

"""
This script is run inside blender, and will stream the meshes as you move the tiny van moves around the scene. Run from test_meshes.blend.
"""

def load_for(x, y, mesh_collection, pad=30, chunk_size=10):

    origin = [598458.0, 262469.5] # 27700

    global runs
    runs += 1

    empty = bpy.data.objects.new( "empty", None )
    mesh_collection.objects.link( empty )

    req = f"http://dt.twak.org:5000/v0/find-mesh?w={origin[0]+x-pad}&n={origin[1]+y+pad}&e={origin[0]+x+pad}&s={origin[1]+y-pad}&scale={chunk_size}"
    print(f"request: {req}")
    with urllib.request.urlopen(req) as response:
        html = response.read()
        for data in json.loads( html ):
            folder = data[0]
            x,y = data[1]- origin[0], data[2]-origin[1]
            files = data[3].split(";")
            fbx_file = None
            nas = data[4]

            print (f"loading {folder} to {x},{y}")
            
            for file in files:
                if file in bpy.data.objects:
                    continue

                dest = os.path.join(scratch + nas, file)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not os.path.exists(dest):
                    print(f"downloading {file}")
                    shutil.copyfile( f"/home/twak/citnas{nas}/{file}",dest)
                if file.endswith(".fbx"):
                    fbx_file = file
                    
            if fbx_file is not None:
                if fbx_file in bpy.data.objects:
                    print(f"skipping existing {fbx_file}")
                    continue
                bpy.context.view_layer.active_layer_collection =  bpy.context.view_layer.layer_collection.children.get(mesh_collection.name)
                bpy.ops.import_scene.fbx(filepath=f"{scratch+nas}/{fbx_file}")
                for o in bpy.context.selected_objects: # created meshes
                    o.location.x += x
                    o.location.y += y
                    o.name = file
                    if not o.name in mesh_collection.objects:
                        mesh_collection.objects.link(o)
                    o.parent = empty


def on_transform_completed(obj, scene):

    # when the van moves, load a window around it
    loc = bpy.context.scene.objects["van"].location    
    mesh_collection = bpy.data.collections["Collection"]
    load_for(loc.x, loc.y, mesh_collection, pad=20, chunk_size=10)

    # select the van again
    bpy.context.active_object.select_set(False)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    bpy.context.scene.objects["van"].select_set(True)

def on_depsgraph_update(scene, depsgraph):
    if on_depsgraph_update.operator is None:
        on_depsgraph_update.operator = bpy.context.active_operator
        return 
    if on_depsgraph_update.operator == bpy.context.active_operator:
        return
    on_depsgraph_update.operator = None  # Reset now to not trigger recursion in next step in case it triggers a depsgraph update
    obj = bpy.context.active_object
    if obj.name == 'van':
        on_transform_completed(obj, scene)

if __name__ == '__main__':

    if True: # interactive
        # everytime anything moves (or rotates) - update...
        on_depsgraph_update.operator = None
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    else: # bulk load
        mesh_collection = bpy.data.collections.new(f"mesh_collection_{runs}")
        bpy.context.scene.collection.children.link(mesh_collection)
        load_for(0, 0, pad=100, chunk_size=10)
#        load_for(0, 0, pad=15000, chunk_size=50)
