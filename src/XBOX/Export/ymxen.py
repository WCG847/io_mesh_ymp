from io import BytesIO
from struct import Struct, pack
from typing import Iterable
import math
import bpy
from mathutils import Matrix

class YMXEN:
	ymxenBone = Struct('>16s4f4f4i4f')
	AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, 'X').inverted()

	tag = b'YOBJ'
	def __init__(self, collections: list[bpy.types.Collection], armature: bpy.types.Object, textures: list[bpy.types.Image]):
		if collections is None or armature is None or textures is None:
			raise ValueError('Args not provided')# go home
		self.collections = collections
		self.armature = armature
		self.textures = textures
		self.structs: list[BytesIO] = []

	def write(self):
		self.write_armature()
		for col in self.collections:
			self.write_collections(col, len(col.objects)) # only used as a editor side metadata so count doesnt matter

	def write_collections(self, col: bpy.types.Collection, count: int): ...
	def write_armature(self):
		arm = self.armature.data
		bone_index = {b: i for i, b in enumerate(arm.bones)}

		bone = BytesIO()
		for bpy_bone in arm.bones:
			if bpy_bone.parent:
				matrix = bpy_bone.parent.matrix_local.inverted() @ bpy_bone.matrix_local
			else:
				matrix = bpy_bone.matrix_local
			matrix = YMXEN.AXIS_FIX @ matrix

			parent_index = bone_index.get(bpy_bone.parent, -1)
			rot = matrix.to_3x3().normalized()
			loc = matrix.to_translation()

			bone.write(YMXEN.ymxenBone.pack(bpy_bone.name.encode('shift_jis').ljust(16, b'\x00'), *loc, 0.0,  *rot.to_euler('ZYX'), 0.0, parent_index, 0, 0, 0, 0.0, 0.0, 0.0, 0.0))
		self.structs.append(bone)