import bpy
import shutil

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
import utils
"""
converts merged point clouds + textures into an fbx file

see pts_to_defect_mesh.py for the pdal pipeline that generates the input files
see pts_to_mesh.py/.blend for more info.
"""


name = "w_1"  # debug!
root = f"{utils.scratch}/foo"

for s in sys.argv[1:]:
    if s.startswith("--name="):
        name = s.split("=")[1].replace('""',"")
    if s.startswith("--root="):
        root = s.split("=")[1].replace('""',"")

root = root+"/"+name

print (sys.argv[1:])
print (f"processing {root}")

input_folder = os.path.join ( root, "stage2" )
output_folder = os.path.join (root, "stage3" )

pavement_image = bpy.data.images.load(os.path.join(input_folder, f"pavement.jpg"))
im_w, im_h = pavement_image.size

for target in ["defect"]:

    # hack when developing
    if target in bpy.context.scene.objects:
        objs = bpy.data.objects
        objs.remove(objs[target], do_unlink=True)

    # load the point cloud
    print(os.path.join(input_folder,f"{target}.ply"))
    bpy.ops.wm.ply_import(filepath=os.path.join(input_folder,f"{target}.ply"))

    # points to mesh
    v = bpy.context.scene.objects[target]
    mod = v.modifiers.new(target, 'NODES')
    mod.name = target
    mod.node_group = bpy.data.node_groups[target]
    bpy.ops.object.modifier_apply(modifier=mod.name)

    # add uv layer
    v.data.uv_layers.new(name="uv")

    # project uvs from overhead (also for vegetation, but we don't use it)
    me = v.data
    new_uv = v.data.uv_layers[0]

    dim_w, dim_h = v.dimensions.xy

    for face in me.polygons:
        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
            l = me.vertices [vert_idx ].co.xy
            new_uv.data[loop_idx].uv = [l.x / dim_w, l.y / dim_h]
            # new_uv.data[loop_idx].uv = [l.x , l.y]

    # for some reason, we have 2 materials. delete the first.
    v.data.materials.pop(index=0)

t = bpy.context.scene.objects["defect"]

t.material_slots[0].material.node_tree.nodes["orthomosaic"].image = pavement_image

# save the fbx file
for target in ["defect"]:
    bpy.context.scene.objects[target].select_set(True)

bpy.ops.export_scene.fbx(filepath=os.path.join(output_folder, f"{name}_mesh.fbx"), use_selection=True)
shutil.copyfile(os.path.join(input_folder, "pavement.jpg"), os.path.join ( output_folder, "pavement.jpg") )




