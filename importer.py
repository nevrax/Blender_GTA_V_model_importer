if "bpy" in locals():
    import importlib
    importlib.reload(file_parser)
else:
    from . import file_parser

import bpy
import os
from mathutils import (Vector, Quaternion, Matrix, Euler)

bone_mapping = []
skeleton = None
vertexStructures = {
    "N209731BE": {"pos": 0, "normal": 1, "color": 2, "uv": 3},
    "N51263BB5": {"pos": 0, "normal": 1, "color": 2, "uv": 3, "undef3": 4},
    "S9445853F": {"pos": 0, "weights": 1, "bone_indices": 2, "normal": 3, "color": 4, "uv": 5, "undef3": 6},
    "S12D0183F": {"pos": 0, "weights": 1, "bone_indices": 2, "normal": 3, "color": 4, "undef1": 5, "uv": 6, "uv2": 7, "undef3": 8},
    "SD7D22350": {"pos": 0, "weights": 1, "bone_indices": 2, "normal": 3, "color": 4, "undef1": 5, "uv": 6, "undef3": 7},
    "SBED48839": {"pos": 0, "weights": 1, "bone_indices": 2, "normal": 3, "color": 4, "undef1": 5, "uv": 6},
    "NC794193B": {"pos": 0, "normal": 1, "color": 2, "bone_indices": 3, "uv": 4, "uv2": 5, "undef1": 5}
}

def getNameFromFile(filepath):
    return os.path.basename(filepath).split(".")[0]


def getMaterial(shaders, shader_index, mesh_name, **kwargs):

    def getShaderNode(mat):
        shader_node = node_out.inputs['Surface'].links[0].from_node
        return shader_node

    def getShaderInput(mat, name):
        shaderNode = getShaderNode(mat)
        return shaderNode.inputs[name]

    def getSampler(sampler_name, **kwargs):
        dot_split = sampler_name.split(".")
        if len(dot_split) > 1:
            sampler_name = dot_split[0]
        image_name = sampler_name.lower()
        image_file = image_name + ".dds"
        split = image_name.split("\\")
        image_path = ""
        path_variants = []

        if len(split) > 1:
            path_variants.append(os.path.join(kwargs["folder"], split[0], split[1] + ".dds"))
            path_variants.append(os.path.join(kwargs["folder"], split[1] + ".dds"))
            path_variants.append(os.path.join(kwargs["folder"], os.path.pardir, split[0], split[1] + ".dds"))
        else:
            path_variants.append(os.path.join(kwargs["folder"], image_file))
            path_variants.append(os.path.join(kwargs["folder"], os.path.pardir, image_file))
            path_variants.append(os.path.join(kwargs["folder"], os.path.pardir, image_name, image_file))

        for path in path_variants:
            if os.path.exists(path):
                image_path = path
                break

        if image_path:
            teximage_node = ntree.nodes.new('ShaderNodeTexImage')
            img = bpy.data.images.load(image_path, check_existing=True)
            img.name = kwargs["name"]+ "_" + image_name
            teximage_node.image = img
            return teximage_node
        else:
            print('sampler not found! "{0}"'.format(path_variants))
            return None

    # Get material
    mat_name = kwargs["name"]+ "_" + mesh_name + str(shader_index)
    mat = bpy.data.materials.get(mat_name)

    if mat is None:
        # create material
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        ntree = mat.node_tree
        node_out = ntree.get_output_node('EEVEE')
        shader = getShaderNode(mat)
        links = ntree.links
        # add diffuse map
        colorInput = getShaderInput(mat, 'Base Color')
        teximage_node = getSampler(shaders["members"][shader_index]["DiffuseSampler"], **kwargs)
        if teximage_node:
            teximage_node.interpolation = 'Smart'

            # blend mode
            mat.blend_method = 'CLIP'
            mat.shadow_method = 'CLIP'

            links.new(teximage_node.outputs['Color'],colorInput)
            transparent_shader = ntree.nodes.new('ShaderNodeBsdfTransparent')
            mix_shader = ntree.nodes.new('ShaderNodeMixShader')
            # link transparent shader
            links.new(teximage_node.outputs[1], mix_shader.inputs[0])
            links.new(mix_shader.outputs[0], node_out.inputs['Surface'])
            links.new(transparent_shader.outputs[0], mix_shader.inputs[1])
            links.new(shader.outputs[0], mix_shader.inputs[2])


        # add normal map
        teximage_node = getSampler(shaders["members"][shader_index]["BumpSampler"], **kwargs)
        if teximage_node:
            teximage_node.interpolation = 'Smart'
            normalMap_node = ntree.nodes.new('ShaderNodeNormalMap')
            if shaders["members"][shader_index]["Bumpiness"]:
                normalMap_node.inputs[0].default_value = float(shaders["members"][shader_index]["Bumpiness"])

            teximage_node.image.colorspace_settings.name = 'Raw'

            # invert greenchannel
            seperateRGB = ntree.nodes.new("ShaderNodeSeparateRGB")
            links.new(teximage_node.outputs['Color'], seperateRGB.inputs[0])

            invertNode = ntree.nodes.new("ShaderNodeInvert")
            links.new(seperateRGB.outputs[1], invertNode.inputs[1])
            combineRGB = ntree.nodes.new("ShaderNodeCombineRGB")
            links.new(invertNode.outputs[0], combineRGB.inputs[1])
            links.new(seperateRGB.outputs[0], combineRGB.inputs[0])
            links.new(seperateRGB.outputs[2], combineRGB.inputs[2])

            links.new(combineRGB.outputs[0], normalMap_node.inputs['Color'])
            links.new(normalMap_node.outputs['Normal'], shader.inputs['Normal'])

        # add specular map
        teximage_node = getSampler(shaders["members"][shader_index]["SpecSampler"], **kwargs)
        if teximage_node:
            teximage_node.interpolation = 'Smart'
            seperateRGB = ntree.nodes.new("ShaderNodeSeparateRGB")
            links.new(teximage_node.outputs['Color'], seperateRGB.inputs[0])
            links.new(seperateRGB.outputs[2], shader.inputs[5])



    return mat


def setVertexAttributes(Obj, mesh, VertexData, VertexDeclaration, skinned):
    global bone_mapping
    mesh.uv_layers.new(name="UVMap")
    uvlayer = mesh.uv_layers.active.data
    mesh.calc_loop_triangles()
    normals = []

    # get vertex mapping
    normalIndex = vertexStructures[VertexDeclaration]["normal"]
    uvIndex = vertexStructures[VertexDeclaration]["uv"]
    if skinned:
        boneIndex = vertexStructures[VertexDeclaration]["bone_indices"]
        weightIndex = vertexStructures[VertexDeclaration]["weights"]

    for i, lt in enumerate(mesh.loop_triangles):
        for loop_index in lt.loops:
            # set uv coordinates
            uvlayer[loop_index].uv = VertexData[mesh.loops[loop_index].vertex_index][uvIndex]
            # flip y axis
            uvlayer[loop_index].uv[1] = 1 - uvlayer[loop_index].uv[1]
            # set normals (1)
            normals.append(VertexData[mesh.loops[loop_index].vertex_index][normalIndex])
            # add bone weights
            if skinned:
                # bone indices (4)
                for i, vg in enumerate(VertexData[mesh.loops[loop_index].vertex_index][boneIndex]):
                    vg_name = bone_mapping[int(vg)]
                    if not vg_name in Obj.vertex_groups:
                        group = Obj.vertex_groups.new(name=vg_name)
                    else:
                        group = Obj.vertex_groups[vg_name]
                    # bone weights (3)
                    weight = VertexData[mesh.loops[loop_index].vertex_index][weightIndex][i]
                    if weight > 0.0:
                        group.add([mesh.loops[loop_index].vertex_index], weight, 'REPLACE' )

    # normal custom verts
    mesh.use_auto_smooth = True
    mesh.normals_split_custom_set(normals)



def findArmature(skel_file):
    # try to get the existing armature by name
    global skeleton, bone_mapping
    skel_name = os.path.basename(skel_file).split(".")[0]
    if skel_name in bpy.data.objects and bpy.data.objects[skel_name].type == 'ARMATURE':
        skeleton = bpy.data.objects[skel_name]
        for bone in skeleton.pose.bones:
            bone_mapping.append(bone.name)
        return True
    else:
        return False


def importMesh(filepath, shaders, skinned=False, create_materials=False, **kwargs):
    global skeleton, bone_mapping
    p = file_parser.GTA_Parser()
    p.read_file(filepath)
    base_name = getNameFromFile(filepath)

    objects = []
    for num, geometry in enumerate(p.data["members"][0]["members"][1]["members"]):
        name = base_name + str(num)
        faces = geometry["members"][0]["faces"]
        verts = geometry["members"][1]["positions"]
        shader_index = int(geometry["ShaderIndex"])
        skinned_mesh = p.data["members"][0]["Skinned"] == "True"
        bone_count = int(p.data["members"][0]["BoneCount"])

        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, (), faces)

        # find skelton
        if skinned_mesh and not skeleton and "odd_root" in kwargs:
            skel_file = find_in_folder(kwargs["odd_root"], extension=".skel")
            if skel_file:
                if not findArmature(skel_file):
                    loadSkeleton(skel_file, **kwargs)
            if not skel_file or len(bone_mapping) != bone_count:
                print("no skeleton file or armature found for: {0}".format(filepath))

        if not mesh.validate():
            VertexDeclaration = geometry["VertexDeclaration"]
            Obj = bpy.data.objects.new(name, mesh)
            setVertexAttributes(Obj, mesh, geometry["members"][1]["vertices"], VertexDeclaration, skinned_mesh)
            bpy.context.scene.collection.objects.link(Obj)
            Obj.select_set(True)
            objects.append(Obj)
            bpy.context.view_layer.objects.active = Obj
            if create_materials:
                # Assign material to object
                mat = getMaterial(shaders, shader_index, base_name, **kwargs)
                Obj.data.materials.append(mat)

    if bpy.context.view_layer.objects.active:
        # join all submeshes
        if len(objects) > 1:
            bpy.ops.object.join()

        bpy.context.view_layer.objects.active.name = base_name
        activeObject = bpy.context.view_layer.objects.active

        # apply armature modifier
        if skinned_mesh and skeleton:
            mod = activeObject.modifiers.new("armature", 'ARMATURE')
            mod.object = skeleton
            activeObject.parent = skeleton

        activeObject.select_set(False)
        return activeObject
    else:
        return None


def buildArmature(skel_file):
    arma = bpy.data.armatures.new(os.path.basename(skel_file.name))
    Obj = bpy.data.objects.new(os.path.basename(skel_file.name), arma)
    bpy.context.scene.collection.objects.link(Obj)
    bpy.context.view_layer.objects.active = Obj
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    numBones = skel_file.data["members"][0]["NumBones"]

    def addBone(bone, armature, obj, parent=None):
        global bone_mapping

        bone_name = bone["attributes"][0]
        bone_mapping.append(bone_name)
        b_bone = armature.edit_bones.new(bone_name)
        b_bone.head = (0,0,0)
        b_bone.tail = (0,0.05,0)
        b_bone.use_inherit_rotation = True
        b_bone.use_local_location = True
        quad = Quaternion((float(bone["RotationQuaternion"][3]), float(bone["RotationQuaternion"][0]),
            float(bone["RotationQuaternion"][1]), float(bone["RotationQuaternion"][2])))
        # quad = Quaternion(map(float, bone["RotationQuaternion"]))
        mat = quad.to_matrix().to_4x4()
        b_bone.matrix = mat
        position = Vector(map(float, bone["LocalOffset"]))
        b_bone.translate(position)
        if parent:
            b_bone.parent = parent
            b_bone.matrix = parent.matrix @ b_bone.matrix

        # add child bones
        for children in bone["members"]:
            for child in children["members"]:
                addBone(child, armature, obj, b_bone)

    addBone(skel_file.data["members"][0]["members"][0], arma, Obj)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    return Obj


def find_in_folder(folder, file_name=None, extension=None):
    for root, dirs, files in os.walk(folder, topdown=False):
        for file in files:
            print(os.path.join(root, file))
            if extension:
                if file.endswith(extension):
                    return os.path.join(root, file)
            else:
                if file.endswith(file_name):
                    return os.path.join(root, file)
    return None


def loadSkeleton(filepath, **kwargs):
    global skeleton
    skel_file = file_parser.GTA_Parser()
    if skel_file.read_file(filepath):
        skeleton = buildArmature(skel_file)
        return True
    else:
        print(filepath)
        print("skel file not found")
        return False


def loadODR(filepath, **kwargs):
    global skeleton
    kwargs["odr_root"] = os.path.dirname(filepath)
    kwargs["odr_name"] = os.path.basename(filepath).split(".")[0]
    odrFile = file_parser.GTA_Parser()
    odrFile.read_file(filepath)
    name = getNameFromFile(filepath)
    lodgroup = odrFile.getMemberByName("LodGroup")
    shaders = odrFile.getMemberByName("Shaders")
    skel = odrFile.getMemberByName("Skeleton")

    # check for odr skeleton
    if skel != "null" and not skeleton:
        kwargs["odr_skeleton_path"] = os.path.join(kwargs["folder"], *skel.split("\\"))
        if os.path.exists(kwargs["odr_skeleton_path"]):
            loadSkeleton(kwargs["odr_skeleton_path"], **kwargs)
        else:
            print("missing odr skeleton file: {0}".format(kwargs["odr_skeleton_path"]))

    mesh_path = ""
    for key, value in lodgroup["members"][0].items():
        if name in key and key.endswith(".mesh"):
            mesh_path = os.path.join(kwargs["folder"], *key.split("\\"))
    return importMesh(mesh_path, shaders, **kwargs)


def loadODD(filepath, **kwargs):
    kwargs["odd_root"] = os.path.dirname(filepath)
    kwargs["odd_name"] = os.path.basename(filepath).split(".")[0]
    oddFile = file_parser.GTA_Parser()
    oddFile.read_file(filepath)
    root = oddFile.getMemberByName("Version")
    mesh_list = []
    base_path = kwargs["folder"]

    # check for odd skeleton
    kwargs["odd_skeleton_path"] = os.path.join(kwargs["odd_root"], kwargs["odd_name"], kwargs["odd_name"] + ".skel")
    if os.path.exists(kwargs["odd_skeleton_path"]):
        if not findArmature(kwargs["odd_skeleton_path"]):
            loadSkeleton(kwargs["odd_skeleton_path"], **kwargs)
    for odr in root["values"]:
        odr_path = os.path.join(base_path, *odr.split("\\"))
        kwargs["folder"] = os.path.dirname(odr_path)
        mesh_list.append(loadODR(odr_path, **kwargs))
    return mesh_list


def deselectAll():
    for obj in bpy.data.objects:
        obj.select_set(False)


def load(operator, context, filepath="", import_armature=True, **kwargs):
    global bone_mapping, skeleton
    skeleton = None
    bone_mapping = []

    def message(self, context):
        self.layout.label(text="failed to import model!")

    bpy.context.view_layer.objects.active = None

    deselectAll()


    if kwargs["file_extension"] == "odr":
        meshObjects = [loadODR(filepath, **kwargs)]
    if kwargs["file_extension"] == "odd":
        meshObjects = loadODD(filepath, **kwargs)


    if not meshObjects:
        bpy.context.window_manager.popup_menu(message, title="Error", icon='ERROR')
    return {'FINISHED'}