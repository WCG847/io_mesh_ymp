from typing import Iterable
import warnings
import math
import bpy
from mathutils import Euler, Matrix, Vector


def emit_strip_faces(strip, faces):
	for t in range(len(strip) - 2):
		a, b, c = (
			(strip[t + 1], strip[t], strip[t + 2])
			if (t & 1)
			else (strip[t], strip[t + 1], strip[t + 2])
		)
		if a == b or b == c or a == c:
			continue
		faces.append((a, b, c))


def get_view(src: memoryview, offset: int):
	b = src.cast("B")
	i = b.cast("I")
	return b[i[offset // 4] :]


def link(obj: bpy.types.Object, mode="EDIT"):
	bpy.context.collection.objects.link(obj)
	bpy.context.view_layer.objects.active = obj
	obj.select_set(True)

	bpy.ops.object.mode_set(mode="OBJECT")
	if mode != "OBJECT":
		bpy.ops.object.mode_set(mode=mode)


class SkinModel:
	AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, "X")

	def __init__(self, file: memoryview, scale: float):
		if file:
			self.file = file.cast("I")
			self.scale = scale
			self.create()

	def create(self):
		AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, "X")

		s = bpy.data.armatures.new("0")
		self.armature = bpy.data.objects.new("ympBone", s)
		NULL = -1
		if (bone_count := self.file[5]) <= 0:
			warnings.warn("No bones. skipping", BytesWarning)
		else:
			assert (bone := get_view(self.file, 32)) != NULL
			link(self.armature)
			self.bones: list[bpy.types.EditBone] = [None] * bone_count
			self.world = [Matrix.Identity(4) for i in range(bone_count)]
			self.local = [Matrix.Identity(4) for i in range(bone_count)]
			for i in range(bone_count):
				b = bone[i * 80 : (i * 80) + 80]
				name = (
					b.cast("c")[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
				)
				bpy_bone = self.armature.data.edit_bones.new(name)
				self.bones[i] = bpy_bone

				px, py, pz = b[16:28].cast("f")
				rx, ry, rz = b[32:44].cast("f")
				positions = Vector((px, py, pz))
				rotations = Euler((rx, ry, rz), "ZYX")
				parent = b[48:].cast("i")[0]
				local = Matrix.LocRotScale(positions, rotations, None)

				if parent == NULL:
					self.world[i] = AXIS_FIX @ local
				else:
					self.world[i] = self.world[parent] @ local

					bpy_bone.parent = self.bones[parent]

			DEFAULT_LEN = 0.05 * self.scale

			parents = [
				bone[i * 80 : (i * 80) + 80][48:].cast("i")[0]
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

	def set_texture(self, paths: Iterable[str]):
		if (tex_count := self.file[6]) <= 0:
			warnings.warn("No texs. skipping", BytesWarning)
		else:
			assert (texture := get_view(self.file, 36)) != -1
			for i in range(tex_count):
				t = texture[i * 16 : (i * 16) + 16].cast("c")
				name = t[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
				if name:
					for path in paths:
						assert path.upper().endswith(".TGA")
						if name.upper() in path.upper():
							tex = bpy.data.images.load(path, check_existing=True)
							self.tex_array.append(tex)

	def start(self):
		object_groups = get_view(self.file, 40)
		assert object_groups != -1
		obj_g_count = self.file[11]

		self.cols: list[bpy.types.Collection] = []
		for i in range(obj_g_count):
			o = object_groups[i * 32 : (i * 32) + 32].cast("c")
			name = o[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
			collect = bpy.data.collections.new(name)
			bpy.context.scene.collection.children.link(collect)
			self.cols.append(collect)

		subobject_count = self.file[4]
		subobject_ptr = get_view(self.file, 28)
		for i in range(subobject_count):
			_ = bpy.data.meshes.new("ympSubObject")

			bpy_obj = bpy.data.objects.new(f"Object{i:02d}", _)
			subobj = subobject_ptr[i * 64 : (i * 64) + 64]
			skin_tbl_count, uv_count, a, b, og_index, c, d, e = subobj[:32].cast("I")
			self.cols[og_index].objects.link(bpy_obj)
			f = self.file.cast("B")
			sub = subobj.cast("I")
			skin_stream = f[sub[2] :]
			primitive_stream = f[sub[3] :]
			vertex_colour = f[sub[7] :]
			colour_count = sub[9]
			bounding_sphere = subobj[48:64].cast("f")
			centre = SkinModel.AXIS_FIX @ Vector(
				(bounding_sphere[0], bounding_sphere[1], bounding_sphere[2])
			)

			radius = bounding_sphere[3]
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
			used = [False] * len(self.bones)
			tables = []
			table_offsets = []
			base_verts = []

			bpy_obj.parent = self.armature
			mod = bpy_obj.modifiers.new(name="Armature", type="ARMATURE")
			mod.object = self.armature

			global_verts, global_norms = self.parse_vertex_buffer(subobj)
			print("GLOBAL VERTS:", len(global_verts))

			tables = []
			for t in range(skin_tbl_count):
				table = self.send_table(skin_stream[t * 32 : (t * 32) + 32])
				tables.append(table)

			used_bones = set()
			for table in tables:
				for b in table["palette"]:
					if b >= 0:
						used_bones.add(b)

			for b in used_bones:
				name = self.bones[b].name
				if name not in bpy_obj.vertex_groups:
					bpy_obj.vertex_groups.new(name=name)
			#self.parse_colours(vertex_colour, colour_count)

			verts, faces, uvs, vtx_weights, out_norms = self.send_primitive_table(
				primitive_stream,
				uv_count,
				tables,
				global_verts,
				global_norms,
			)

			mesh = bpy_obj.data
			mesh.clear_geometry()
			mesh.from_pydata(verts, [], faces)
			mesh.update()

			loop_normals = [None] * len(mesh.loops)

			for poly in mesh.polygons:
				for li, vi in zip(poly.loop_indices, poly.vertices):
					loop_normals[li] = out_norms[vi]
			assert all(loop_normals)
			mesh.normals_split_custom_set(loop_normals)

			uv_layer = mesh.uv_layers.new(name="UVMap")

			for poly in mesh.polygons:
				for li, vi in zip(poly.loop_indices, poly.vertices):
					uv_layer.data[li].uv = uvs[vi] if vi < len(uvs) else (0.0, 0.0)

			for v_idx, ws in vtx_weights.items():
				for bone_idx, w in ws:
					if w <= 0.0:
						continue

					name = self.bones[bone_idx].name

					if name not in bpy_obj.vertex_groups:
						bpy_obj.vertex_groups.new(name=name)

					bpy_obj.vertex_groups[name].add([v_idx], w, "REPLACE")

			mesh.update()
			mesh.calc_loop_triangles()
		bpy.ops.object.mode_set(mode="OBJECT")
		bpy.ops.des

	def parse_vertex_buffer(self, subobj: memoryview):
		f = self.file.cast("B")

		vtx_indirect_ptr = subobj.cast("I")[0x18 // 4]
		vtx_indirect = f[vtx_indirect_ptr:]
		f = self.file.cast("B")
		vtx_indirec = vtx_indirect.cast("I")
		vtx_indirect = f[vtx_indirec[0] :]

		vtx_count = vtx_indirect[0x0E]

		vtx_data = vtx_indirect[0x10:]

		verts: list[Vector] = []

		for i in range(vtx_count):
			x, y, z, _ = vtx_data[i * 16 : (i * 16) + 16].cast("f")
			verts.append(SkinModel.AXIS_FIX @ Vector((x, y, z)))
		size = vtx_count * 16
		packet = vtx_data[size:]
		vtx_data = packet[0x10:]
		norms: list[Vector] = []

		for i in range(vtx_count):
			x, y, z, _ = vtx_data[i * 16 : (i * 16) + 16].cast("f")
			norms.append(SkinModel.AXIS_FIX @ Vector((x, y, z)))
		return verts, norms

	def send_primitive_table(self, stream, count, tables, global_verts, global_norms):
		verts = []
		faces = []
		uvs = []
		weights = {}
		out_norms = []

		f = self.file.cast("B")
		out_vi = 0

		for i in range(count):
			strea = stream[i * 208 : (i * 208) + 208]
			UVS = strea.cast("f")

			U0, V0, _, _ = UVS[0:4]
			U1, V1, _, _ = UVS[4:8]
			uv = (U0 * U1, 1.0 - (V0 * V1))

			info = strea[192:208]
			INFO2 = info.cast("I")
			loop_count = INFO2[1]
			loop_table = INFO2[2]
			LOOPS = f[loop_table:]

			for j in range(loop_count):
				strip = []

				entry = LOOPS[j * 16 : (j * 16) + 16].cast("I")
				block_count = entry[2]
				block_start = f[entry[3] :]

				for k in range(block_count):
					BLOCK = block_start[k * 32 : (k * 32) + 32]
					BI = BLOCK.cast("I")
					BF = BLOCK.cast("f")

					w0, w1, w2 = BF[:3]
					global_vi = BI[3]

					if global_vi < 0 or global_vi >= len(global_verts):
						emit_strip_faces(strip, faces)
						strip.clear()
						continue

					if w0 == 0.0 and w1 == 0.0 and w2 == 0.0:
						emit_strip_faces(strip, faces)
						strip.clear()
						continue

					pos = global_verts[global_vi]
					verts.append(pos.copy())

					out_norms.append(global_norms[global_vi].normalized())

					uvs.append(uv)

					weights[out_vi] = []

					if k < len(tables):
						palette = tables[k]["palette"]

						if w0 > 0 and len(palette) > 0 and palette[0] >= 0:
							weights[out_vi].append((palette[0], w0))
						if w1 > 0 and len(palette) > 1 and palette[1] >= 0:
							weights[out_vi].append((palette[1], w1))
						if w2 > 0 and len(palette) > 2 and palette[2] >= 0:
							weights[out_vi].append((palette[2], w2))

					strip.append(out_vi)
					out_vi += 1

				emit_strip_faces(strip, faces)

		return verts, faces, uvs, weights, out_norms

	def send_table(self, stream: memoryview):
		table = stream.cast("I")
		indices = stream[16:32].cast("i")

		bone_count = table[1]

		palette: list[int] = []
		for i in range(bone_count):
			palette.append(indices[i] - 1 if indices[i] > 0 else -1)

		return {"palette": palette}