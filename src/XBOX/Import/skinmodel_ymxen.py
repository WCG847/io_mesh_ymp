import math
from mathutils import Euler, Matrix, Vector
from ...globals.be import get_view, resolve_view
from struct import unpack_from, unpack
import bpy
import tempfile
import os

def load_dds_from_memory(name: str, data: bytes):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dds")
    tmp.write(data)
    tmp.close()

    img = bpy.data.images.load(tmp.name)
    img.name = name

    return img

def link(obj: bpy.types.Object, mode="EDIT"):
	bpy.context.collection.objects.link(obj)
	bpy.context.view_layer.objects.active = obj
	obj.select_set(True)

	bpy.ops.object.mode_set(mode="OBJECT")
	if mode != "OBJECT":
		bpy.ops.object.mode_set(mode=mode)


class YMXEN_SkinModel:
	AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, "X")

	def __init__(self, file: memoryview, scale: float):
		if not file:
			return
		self.file = file
		self.scale = scale
		self.use_tangents = True if unpack(">I", file[:4])[0] == 16 else False
		self.create()
	def get_texture(self, index: int):
		if index is None:
			return None
		if 0 <= index < len(self.tex_array):
			return self.tex_array[index]
		return None

	def create(self):
		bone_count: int = unpack_from(">I", self.file, 24)[0]
		bone = get_view(self.file, 32)
		s = bpy.data.armatures.new("0")
		self.armature = bpy.data.objects.new("ymxenBone", s)
		NULL = -1
		link(self.armature)
		self.bones: list[bpy.types.EditBone] = [None] * bone_count
		self.world = [Matrix.Identity(4) for i in range(bone_count)]
		self.local = [Matrix.Identity(4) for i in range(bone_count)]
		for i in range(bone_count):
			b = bone[i * 80 : (i * 80) + 80]
			name = b.cast("c")[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
			bpy_bone = self.armature.data.edit_bones.new(name)
			self.bones[i] = bpy_bone
			positions = Vector(unpack_from(">3f", b, 16))
			rotations = Euler(unpack_from(">3f", b, 32), "ZYX")
			parent = unpack_from(">i", b, 48)[0]
			local = Matrix.LocRotScale(positions, rotations, None)

			if parent == NULL:
				self.world[i] = YMXEN_SkinModel.AXIS_FIX @ local
			else:
				self.world[i] = self.world[parent] @ local

				bpy_bone.parent = self.bones[parent]

		DEFAULT_LEN = 0.05 * self.scale
		parents = [
			unpack(">i", bone[i * 80 : (i * 80) + 80][48:52])[0]
			for i in range(bone_count)
		]
		for i, bpy_bone in enumerate(self.bones):
			mat = self.world[i]

			head = mat.to_translation()
			children = [j for j, p in enumerate(parents) if p == i]
			if not children:
				bpy_bone.use_deform = False
				bpy_bone.hide = True
			if children:
				child_head = self.world[children[0]].to_translation()
				vec = child_head - head
				direction = vec.normalized()
				length = vec.length
			else:
				rot = mat.to_quaternion()
				direction = rot @ Vector((0, 1, 0))
				length = DEFAULT_LEN

			bpy_bone.head = head
			bpy_bone.tail = head + direction * max(length, 1e-5)
			bpy_bone.align_roll(mat.to_3x3() @ Vector((0, 0, 1)))

		self.tex_array: list[bpy.types.Image] = []

	def set_textures(self, filepack: memoryview):
		header = filepack.cast('I') # little endian so its fine.
		count = header[0]
		assert count > 0
		body = filepack[16:]
		for i in range(count):
			START = i * 32
			END = START + 32
			got = body[START:END]
			name = got.cast('c')
			name = name[:16]
			ext = got[16:20]
			fields = got.cast('I')
			fields = fields[20//4:32//4]
			print(got.tobytes())
			tex_name = name.tobytes().split(b'\x00')[0].decode('shift_jis')
			extension = ext.tobytes().split(b'\x00')[0].decode('shift_jis')
			assert extension == 'dds'
			size = fields[0]
			offset = fields[1]
			data = filepack[offset:offset+size]
			img = load_dds_from_memory(tex_name, data)
			self.tex_array.append(img)
		self.reorder_texture()

	def start(self):
		object_groups = get_view(self.file, 40)
		assert object_groups != -1
		obj_g_count = unpack_from(">I", self.file, 44)[0]
		self.cols: list[bpy.types.Collection] = []
		for i in range(obj_g_count):
			o = object_groups[i * 32 : (i * 32) + 32].cast("c")
			name = o[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
			collect = bpy.data.collections.new(name)
			bpy.context.scene.collection.children.link(collect)
			self.cols.append(collect)
		SIZEOF = 184 if self.use_tangents else 180
		subobject_count = unpack_from(">I", self.file, 16)[0]
		subobject_ptr = get_view(self.file, 20)
		for i in range(subobject_count):
			_ = bpy.data.meshes.new("ymxenSubObject")

			bpy_obj = bpy.data.objects.new(f"Object{i:02d}", _)
			subobj = subobject_ptr[i * SIZEOF : (i * SIZEOF) + SIZEOF]
			vertex_count, unk_bool, bone_count = unpack(">3I", subobj[:12])
			unk_bool = bool(unk_bool)  # treated as 32-bit, akin to Windows' BOOL
			bone_indices = unpack(">20i", subobj[12:92])  # dont ask
			(
				bone_weight_count,
				og_index,
				unk_bool_2,
				vert_offset,
				weight_offset,
				uv_offset,
			) = unpack(">6I", subobj[92:116])
			# Custom tangents is a bit tricky in Blender, we just calculate it automatically
			if self.use_tangents:
				# earlier revisions neglected this field in serialisation
				tangent_offset = unpack(">I", subobj[116:120])[0]
			else:
				tangent_offset = None  # just use Blender's default tangents
			fmt = ">I16s7If3f"
			offset = 120 if self.use_tangents else 116

			(
				effect_technique_index,
				shader_name,
				unk_int_1,
				unk_int_2,
				material_count,
				material_offset,
				batch_offset,
				redundant_vertex_count,
				unk_int_3,
				radius,
				cx,
				cy,
				cz,
			) = unpack_from(fmt, subobj, offset)

			centre = (cx, cy, cz)

			material = resolve_view(self.file, material_offset)
			batch = resolve_view(self.file, batch_offset)
			vertices = resolve_view(self.file, vert_offset)
			weights = resolve_view(self.file, weight_offset)
			uvs = resolve_view(self.file, uv_offset)
			if tangent_offset:
				tangent = resolve_view(self.file, tangent_offset)
			else:
				tangent = None
			self.cols[og_index].objects.link(bpy_obj)
			centre = YMXEN_SkinModel.AXIS_FIX @ Vector(centre)
			sphere = bpy.data.objects.new(f"ySphere_{i:02d}", None)
			sphere.empty_display_type = "SPHERE"
			sphere.empty_display_size = radius
			sphere.location = centre
			self.cols[og_index].objects.link(sphere)

			sphere.parent = bpy_obj
			sphere.hide_select = True
			sphere.hide_render = True
			sphere.hide_viewport = True

			bpy_obj.display_type = "TEXTURED"
			bpy_obj.parent = self.armature
			mod = bpy_obj.modifiers.new(name="Armature", type="ARMATURE")
			mod.object = self.armature
			for b in bone_indices:
				if b != -1:
					name = self.bones[b].name
					if name not in bpy_obj.vertex_groups:
						bpy_obj.vertex_groups.new(name=name)
			NORMALS, XYZS, DIFFUSES = self.send_fvf(vertex_count, vertices, bpy_obj)
			bone_weights = self.send_weights(bone_weight_count, weights, bpy_obj, bone_count)
			faces = self.send_faces(batch, bpy_obj)
			bpy_obj.data.from_pydata(XYZS, [], faces)
			bpy_obj.data.normals_split_custom_set_from_vertices(NORMALS)
			UVS = self.send_TEXCOORD(uvs, vertex_count)

			mesh = bpy_obj.data
			uv_layer = mesh.uv_layers.new(name="TEXCOORD0").data

			for poly in mesh.polygons:
				for loop_idx in poly.loop_indices:
					vert_idx = mesh.loops[loop_idx].vertex_index
					uv_layer[loop_idx].uv = UVS[vert_idx]

			col = bpy_obj.data.color_attributes.new(
			name="D3DFVF_DIFFUSE",
			domain='POINT',
			type='BYTE_COLOR'
		)

			for i, d in enumerate(DIFFUSES):
				a = (d >> 24) & 0xFF
				r = (d >> 16) & 0xFF
				g = (d >> 8) & 0xFF
				b = d & 0xFF
				col.data[i].color = (r, g, b, a)
			for group, (bone_index, weights) in zip(bpy_obj.vertex_groups, bone_weights):
				for v_idx, w in enumerate(weights):
					group.add([v_idx], w, 'REPLACE')
			mesh.calc_tangents(uvmap="TEXCOORD0")
			self.set_shader(shader_name.split(b'\x00')[0].decode('shift_jis'), effect_technique_index, material, material_count, bpy_obj)

	def set_shader(self, name: str, effect_technique_index: int, material: memoryview, material_count: int, subobj: bpy.types.Object):
		mat = bpy.data.materials.new(name=name)
		nodes = mat.node_tree.nodes
		links = mat.node_tree.links
		nodes.clear()
		out = nodes.new("ShaderNodeOutputMaterial")
		bsdf = nodes.new("ShaderNodeBsdfPrincipled")
		links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
		for i in range(material_count):
			START = i * 4
			END = (i * 4) + 4
			got = material[START:END]
			offset = unpack('>I', got)[0]
			material_view = resolve_view(self.file, offset)
			MAT_name = unpack_from('16s', material_view, 0)[0].split(b'\x00')[0].decode('shift_jis')
			mat_type, mat_size = unpack_from('>2H', material_view, 16)
			match mat_type:
				case 13:
					data = unpack_from('>4f', material_view, 20)
				case 10:
					data = unpack_from('>1f', material_view, 20)
				case 16:
					data = unpack_from('>i', material_view, 20) #microsoft style BOOL

				case 5:
					data = list(unpack_from('>i', material_view, 20))
					if data[0] == -1:
						data[0] = None
					data = tuple(data)

				case 15:
					data = unpack_from('>I', material_view, 20)

			match MAT_name:
				case "g_f4MatAmbCol":
					pass
				case "g_f4MatDifCol":
					r, g, b, a = data
					bsdf.inputs["Base Color"].default_value = (r, g, b, a)
				case "g_f4SpecularCol":
					r, g, b, a = data
					bsdf.inputs["Specular Tint"].default_value = (r, g, b, 1.0)


				case "g_fSpecularLev":
					(v,) = unpack_from('>f', material_view, 20)
					bsdf.inputs["Specular IOR Level"].default_value = v


				case "g_iSpecularPow":
					(p,) = unpack_from('>I', material_view, 20)
					bsdf.inputs["Roughness"].default_value = max(0.0, min(1.0, 1.0 - (p / 128.0)))

				case "g_fHDRAlpha":
					pass
				case "g_bUseRefRegMap":
					pass
				case "g_bReflectAdd":
					pass
				case "g_fReflectAlpha":
					pass
				case "g_fSweatLev":
					pass
				case "texDiffuse":
					tex_idx = data[0]
					img = self.get_texture(tex_idx - 1)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img
						tex.interpolation = 'Linear'
						links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

				case "texSpecularMap":
					tex_idx = data[0]
					img = self.get_texture(tex_idx - 1)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img
						tex.image.colorspace_settings.name = 'Non-Color'

						inv = nodes.new("ShaderNodeInvert")
						links.new(tex.outputs["Color"], inv.inputs["Color"])
						links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])

				case "texNormal":
					tex_idx = data[0]
					img = self.get_texture(tex_idx - 1)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img
						tex.image.colorspace_settings.name = 'Non-Color'

						nrm = nodes.new("ShaderNodeNormalMap")
						links.new(tex.outputs["Color"], nrm.inputs["Color"])
						links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])

				case "texSphRefction":
					pass
				case "texRefctionReg":
					pass
				case _:
					pass
		subobj.data.materials.append(mat)


	def reorder_texture(self):
		textures = get_view(self.file, 0x24)
		tex_array = []
		texture_count = unpack_from('>I', self.file, 0x1C)[0]
		for i in range(texture_count):
			START = i * 16
			END = START + 16
			view = textures[START:END]
			name = unpack('16s', view)[0].split(b'\x00')[0].decode('shift_jis')
			print(f'Texture in YMXEN {name}')
			for tex in self.tex_array:
				if name.lower() == 'cubemap':
					continue
				if tex.name.lower() == name.lower():
					print(f'Texture: {tex.name}')
					tex_array.append(tex)
		self.tex_array = tex_array

	def send_TEXCOORD(self, uv: memoryview, vertex: int):
		SIZEOF = 8
		UVS = []
		for i in range(vertex):
			view = uv[i*SIZEOF:(i*SIZEOF)+SIZEOF]
			U, V = unpack('>2f', view)
			V = 1.0 - V
			UVS.append((U, V))
		return UVS

	def send_faces(self, batch: memoryview, subobj: bpy.types.Object):
		MAGIC = 6
		view = batch
		FACES: list[tuple[int, ...]] = []
		while True:
			if unpack('>I', view[:4])[0] != MAGIC:
				break
			view = view[4:]
			face_count = unpack('>I', view[:4])[0]
			view = view[4:]
			face_offset = unpack('>I', view[:4])[0]
			view = view[4:]
			face_view = resolve_view(self.file, face_offset)
			cur_faces = []
			for i in range(face_count):
				cur_faces.append(unpack('>H', face_view[i*2:(i*2)+2])[0])
			FACES.append(tuple(cur_faces))
		faces = []

		for strip in FACES:
			if len(strip) < 3:
				continue

			for i in range(len(strip) - 2):
				a, b, c = strip[i], strip[i + 1], strip[i + 2]

				# Degenerate triangle, skip it
				if a == b or b == c or a == c:
					continue

				# Flip winding every other triangle
				if i & 1:
					faces.append((a, c, b))
				else:
					faces.append((a, b, c))

		mesh = subobj.data
		return faces


	def send_weights(self, count: int, weights: memoryview, subobj: bpy.types.Object, bones: int):
		MORE = 0xFF
		i = 0
		view = weights
		offset = 0
		bone_weights: list[tuple[int, tuple[float, ...]]] = []

		for _ in range(count):
			cur_weig: list[float] = []
			bone_index, weight, status = unpack_from('>IfI', view, offset)
			offset += 16
			cur_weig.append(weight)

			if (status & 0xFF) == MORE:
				while True:
					cur_weig.append(unpack_from('>f', view, offset)[0])
					offset += 4

					idx = unpack_from('>I', view, offset)[0]
					offset += 4
					if 0 <= idx < bones:
						break

			bone_weights.append((bone_index, tuple(cur_weig)))

		return bone_weights


	def send_fvf(self, count: int, vertices: memoryview, subobj: bpy.types.Object):
		packet = unpack('>I', vertices[:4])[0]
		FVF_PACKET = resolve_view(self.file, packet)
		SIZEOF = 28
		NORMALS: list[Vector] = []
		XYZS: list[Vector] = []
		DIFFUSES: list[int] = []
		for i in range(count):
			packet = FVF_PACKET[i*SIZEOF:(i*SIZEOF)+SIZEOF]
			XYZ = YMXEN_SkinModel.AXIS_FIX @ Vector(unpack_from('>3f', packet, 0))
			NORMAL = YMXEN_SkinModel.AXIS_FIX @ Vector(unpack_from('>3f', packet, 12))
			DIFFUSE = unpack_from('>i', packet, 24)[0]
			NORMALS.append(NORMAL)
			XYZS.append(XYZ)
			DIFFUSES.append(DIFFUSE)
		return NORMALS, XYZS, DIFFUSES

		# Create colour attribute