import math
from struct import unpack
import bpy
from mathutils import Euler, Matrix, Vector
from typing import Iterable
import warnings
import bmesh
def get_view(src: memoryview, offset: int):
	b = src.cast("B")
	return b[read_int(b[offset:offset+4], 4, False):]



def link(obj: bpy.types.Object, mode="EDIT"):
	bpy.context.collection.objects.link(obj)
	bpy.context.view_layer.objects.active = obj
	obj.select_set(True)

	bpy.ops.object.mode_set(mode="OBJECT")
	if mode != "OBJECT":
		bpy.ops.object.mode_set(mode=mode)

def read_int(buf, width: int, sign: bool) -> int:
	assert width in {1, 2, 4, 8} and sign in {True, False}
	match width:
		case 1:
			if sign:
				got = 'b'
			else:
				got = 'B'
			return unpack(f'>{got}', buf)[0]
		case 2:
			if sign:
				got = 'h'
			else:
				got = 'H'
			return unpack(f'>{got}', buf)[0]
		case 4:
			if sign:
				got = 'i'
			else:
				got = 'I'
			return unpack(f'>{got}', buf)[0]
		case 8:
			if sign:
				got = 'q'
			else:
				got = 'Q'
			return unpack(f'>{got}', buf)[0]

def read_scalar(buf: memoryview) -> float:
	return unpack('>f', buf)[0]

def read_vector(buf: memoryview) -> Vector:
	return Vector(unpack('>3f', buf))

def read_euler(buf: memoryview) -> Euler:
	return Euler(unpack('>3f', buf), 'ZYX')

def read_fvf(buf: memoryview) -> tuple[Vector, Vector, tuple[float, float, float, float]]:
	POS = read_vector(buf[:3])
	NORM = read_vector(buf[3:6])
	ARGB = read_int(buf[6:9], 4, False)
	a = (ARGB >> 24) & 0xFF
	r = (ARGB >> 16) & 0xFF
	g = (ARGB >> 8) & 0xFF
	b = ARGB & 0xFF
	argb = (
		a / 255.0,
		r / 255.0,
		g / 255.0,
		b / 255.0,
	)

	return (POS, NORM, argb)
def read_name16(name: memoryview) -> str:
	return name[:16].tobytes().split(b'\x00')[0].decode('shift_jis').lower()
class YMXEN_SkinModel:
	AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, "X")
	def __init__(self, buf: memoryview, scale: float):
		if not buf:
			return
		self.scale = scale
		self.buf = buf.cast('B')
		self.create()

	def create(self):
		AXIS_FIX = YMXEN_SkinModel.AXIS_FIX

		s = bpy.data.armatures.new("0")
		self.armature = bpy.data.objects.new("ympBone", s)
		NULL = -1
		if (bone_count := read_int(self.buf[0x18:0x1C], 4, False)) <= 0:
			warnings.warn("No bones. skipping", BytesWarning)
		else:
			assert (bone := get_view(self.buf, 32)) != NULL
			link(self.armature)
			self.bones: list[bpy.types.EditBone] = [None] * bone_count
			self.world = [Matrix.Identity(4) for i in range(bone_count)]
			self.local = [Matrix.Identity(4) for i in range(bone_count)]
			for i in range(bone_count):
				b = bone[i * 80 : (i * 80) + 80]
				name = (
					read_name16(b)
				)
				bpy_bone = self.armature.data.edit_bones.new(name)
				self.bones[i] = bpy_bone

				positions = read_vector(b[16:28])
				rotations = read_euler(b[32:44])
				parent = read_int(b[48:], 4, True)
				local = Matrix.LocRotScale(positions, rotations, None)

				if parent == NULL:
					self.world[i] = AXIS_FIX @ local
				else:
					self.world[i] = self.world[parent] @ local

					bpy_bone.parent = self.bones[parent]

			DEFAULT_LEN = 0.05 * self.scale

			parents = [
				read_int(bone[i * 80 : (i * 80) + 80][48:], 4, True)
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