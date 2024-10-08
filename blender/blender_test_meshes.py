import shutil

import bpy
import json, os
import urllib.request

scratch = "/home/twak/Downloads/mesh_test"
os.makedirs(scratch, exist_ok=True)

"""
This script is run inside blender, and will stream the meshes as you move the tiny van moves around the scene. Run from test_meshes.blend.
"""

def load_for(x, y, pad = 30):

    origin = [598820, 262061] # 27700

    global mesh_collection

    req = f"http://dt.twak.org:5000/v0/find-mesh?w={origin[0]+x-pad}&n={origin[1]+y+pad}&e={origin[0]+x+pad}&s={origin[1]+y-pad}"
    with urllib.request.urlopen(req) as response:
        html = response.read()
        for data in json.loads( html ):
            folder = data[0]
            x,y = data[1]- origin[0], data[2]-origin[1]
            files = data[3].split(";")
            fbx_file = None

            print (f"loading {folder} at {x},{y}")
            
            for file in files:
                if file in bpy.data.objects:
                    continue
                dest = os.path.join(scratch, file)
                if not os.path.exists(dest):
                    shutil.copyfile( f"/home/twak/citnas/08. Researchers/tom/a14/mesh_chunks/{folder}/{file}",dest)
                if file.endswith(".fbx"):
                    fbx_file = file
                    
            if fbx_file is not None:
                if fbx_file in bpy.data.objects:
                    print(f"skipping {fbx_file}")
                    continue
                bpy.context.view_layer.active_layer_collection =  bpy.context.view_layer.layer_collection.children.get(mesh_collection.name)
                bpy.ops.import_scene.fbx(filepath=f"{scratch}/{fbx_file}")
                for o in bpy.context.selected_objects: # created meshes
                    o.location.x += x
                    o.location.y += y
                    o.name = file
                            # mesh_collection.objects.link(o)


def on_transform_completed(obj, scene):

    # when the van moves, load a window around it
    loc = bpy.context.scene.objects["van"].location
    load_for(loc.x, loc.y, pad=20)

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
    on_transform_completed(obj, scene)

if __name__ == '__main__':


    mesh_collection = bpy.data.collections.new("mesh_collection")
    bpy.context.scene.collection.children.link(mesh_collection)
        
    if False: # interactive

        # everytime anything moves (or rotates) - update...
        on_depsgraph_update.operator = None
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    else: # bulk load
        load_for(0, 0, pad=150)
