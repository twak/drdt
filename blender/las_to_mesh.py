import sys

import bpy
import os, sys

"""
Coverts "stage2" of the pts to mesh pipeline outputs to "stage3" using blender.
Run this script from the command line with the following arguments:

root and name describe the location of the las chunks, and the folder containing the las chunks that we will work on.

~/lib/blender-4.2.0-linux-x64/blender -b las_to_mesh.blend --python las_to_mesh.py -- --cycles-device OPTIX --root="/home/twak/Downloads" --name="598550.0_262380.0"

"""


name = "598550.0_262380.0"  # debug!
root = f"/home/twak/Downloads/{name}"

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

for target in ["vegetation", "road"]:

    # hack when developing
    if target in bpy.context.scene.objects:
        objs = bpy.data.objects
        objs.remove(objs[target], do_unlink=True)

    # load the point cloud
    bpy.ops.wm.ply_import(filepath=os.path.join(input_folder,f"{target}.ply"))

    # points to mesh
    v = bpy.context.scene.objects[target]
    mod = v.modifiers.new(target, 'NODES')
    mod.name = target
    mod.node_group = bpy.data.node_groups[target]
    bpy.ops.object.modifier_apply(modifier=mod.name)

    # crop to chunk box
    bmod = v.modifiers.new(target, 'BOOLEAN')
    bmod.object = bpy.context.scene.objects["Cube"]
    bmod.operation = 'INTERSECT'
    bpy.ops.object.modifier_apply(modifier=bmod.name)

    # project uvs from overhead (also for vegetation, but we don't use it)
    me = v.data
    new_uv = v.data.uv_layers[0]

    for face in me.polygons:
        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
            l = me.vertices [vert_idx ].co.xy
            new_uv.data[loop_idx].uv = [l.x/10, l.y/10]

    # for some reason, we have 2 materials. delete the first.
    v.data.materials.pop(index=0)

t = bpy.context.scene.objects["road"]

t.material_slots[0].material.node_tree.nodes["orthomosaic"].image = bpy.data.images.load(os.path.join(input_folder, f"pavement.png"))
t.material_slots[0].material.node_tree.nodes["aerial"     ].image = bpy.data.images.load(os.path.join(input_folder, f"aerial.png"))

img = bpy.data.images.new("pavement",512,512)
img.filepath = os.path.join(output_folder, f"pavement_{name}.jpg")
img.file_format = 'JPEG'

# bake the blended pavement texture
node = t.data.materials[0].node_tree.nodes["bake_placeholder"]
node.image = img

t.select_set(True)
bpy.ops.object.bake(type='DIFFUSE', save_mode='EXTERNAL', filepath=img.filepath)
img.save_render(img.filepath)

t.material_slots[0].material = bpy.data.materials["roadmix_baked"]
t.material_slots[0].material.node_tree.nodes["baked"].image = img

# save the fbx file
for target in ["vegetation", "road"]:
    bpy.context.scene.objects[target].select_set(True)

bpy.ops.export_scene.fbx(filepath=os.path.join(output_folder, f"mesh_{name}.fbx"), use_selection=True)




