from struct import unpack
from typing import Iterable
import warnings
import math
import bpy
from mathutils import Euler, Matrix, Vector


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