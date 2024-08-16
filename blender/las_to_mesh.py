import bpy
import os

"""
Coverts "stage2" of the pts to mesh pipeline outputs to "stage3" using blender.
Run this script from within blender 4.2.

"""

root = "/home/twak/Downloads/598550.0_262380.0"
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

    # project uvs from overhead
    me = v.data

    vert_loops = {}
    for l in me.loops:
        vert_loops.setdefault(l.vertex_index, []).append(l.index)

    new_uv = v.data.uv_layers[0] #.new(name='overhead_ufs')
    # new_uv = v.data.uv_layers.new(name='overhead_ufs')

    for face in me.polygons:
        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
            l =me.vertices [vert_idx ].co.xy
            new_uv.data[loop_idx].uv = [l.x/10, l.y/10]

t = bpy.context.scene.objects["road"]
img = bpy.data.images.new("pavement",512,512)
img.filepath = os.path.join(output_folder, "pavement.jpg")
img.file_format = 'JPEG'

# but the
node = t.data.materials[0].node_tree.nodes["bake_placeholder"]
node.image = img
t.select_set(True)
bpy.ops.object.bake(type='DIFFUSE', save_mode='EXTERNAL', filepath=img.filepath)
img.save_render(img.filepath)

t.material_slots[0].material = bpy.data.materials["roadmix_baked"]
t.material_slots[0].material.node_tree.nodes["baked"].image = img

for target in ["vegetation", "road"]:
    bpy.context.scene.objects[target].select_set(True)

bpy.ops.export_scene.fbx(filepath=os.path.join(output_folder, f"mesh.fbx"), use_selection=True)



