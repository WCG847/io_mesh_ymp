import math
from mathutils import Euler, Matrix, Vector
from ...globals.be import get_view
from struct import unpack_from, unpack
import bpy
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
		self.use_tangents = True if unpack('>I', file[:4])[0] == 16 else False
		self.create()

	def create(self):
		bone_count: int = unpack_from('>I', self.file, 24)[0]
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
			name = (
				b.cast("c")[:16].tobytes().split(b"\x00", 1)[0].decode("shift_jis")
			)
			bpy_bone = self.armature.data.edit_bones.new(name)
			self.bones[i] = bpy_bone
			positions = Vector(unpack_from('>3f', b, 16))
			rotations = Euler(unpack_from('>3f', b, 32), 'ZYX')
			parent = unpack_from('>i', b, 48)[0]
			local = Matrix.LocRotScale(positions, rotations, None)

			if parent == NULL:
				self.world[i] = YMXEN_SkinModel.AXIS_FIX @ local
			else:
				self.world[i] = self.world[parent] @ local

				bpy_bone.parent = self.bones[parent]

		DEFAULT_LEN = 0.05 * self.scale
		parents = [
				unpack('>i', bone[i * 80 : (i * 80) + 80][48:52])[0]
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

	def start(self):
