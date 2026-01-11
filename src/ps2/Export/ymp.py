import bpy
import math
from mathutils import Matrix

def build_vif_packet(NUM: int, type: str):
	allocate = memoryview(bytearray(b'\x00' * 16))
	NUM &= 255
	allocate[14] = NUM
	allocate[15] = 0x6C
	match type:
		case 'POSITIONS':
			IMM = 0
		case 'NORMALS':
			IMM = 0xA0
		case 'COLOURS':
			IMM = 0x280
		case 'BONES':
			IMM = 0x8000
	view2 = allocate.cast('H')
	view2[6] = IMM
	return allocate.toreadonly()
class YMP:
	AXIS_FIX_INV = Matrix.Rotation(math.radians(-90.0), 4, "X").inverted()
	TAG = b'YOBJ'
	def __init__(self, armature_obj: bpy.types.Object, path: str, collections: tuple[bpy.types.Collection]):
		self.obj_groups = collections
		self.path = path
		self.armature_obj = armature_obj

	def write_header(self):
		self.header = memoryview(bytearray(b'\x00' * 64))
		header = self.header.cast('I')
		header[4] = len(self.objs)
		header[5] = len(self.armature.bones)

	def write_armature(self):
		pass
	# get location and rotation. NAME16. 80 block bone