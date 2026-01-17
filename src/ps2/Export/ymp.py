import warnings
import bpy
import math
from mathutils import Matrix, Vector
import math

def write_sphere(min, max):
    C = (
        (min[0] + max[0]) / 2.0,
        (min[1] + max[1]) / 2.0,
        (min[2] + max[2]) / 2.0
    )

    dx = max[0] - C[0]
    dy = max[1] - C[1]
    dz = max[2] - C[2]

    R = math.sqrt(dx*dx + dy*dy + dz*dz)
    return C, R


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

def mem_alloc(size: int):
	if size > 0:
		return memoryview(bytearray(b'\x00' * size))
	else:
		raise MemoryError('cant allocate python memory')
class YMP:
	AXIS_FIX_INV = Matrix.Rotation(math.radians(-90.0), 4, "X").inverted()
	TAG = b'YOBJ'
	def __init__(self, armature_obj: bpy.types.Object, path: str, collections: tuple[bpy.types.Collection]):
		self.obj_groups = collections
		self.path = path
		self.armature_obj = armature_obj

	def write_armature(self):
		SIZEOF = 80
		bones = self.armature_obj.data.bones
		COUNT = len(bones)

		if COUNT == 0:
			raise RuntimeError("Armature has no bones")

		armature = mem_alloc(SIZEOF * COUNT)
		NO_PARENT = -1

		bone_index = {b: i for i, b in enumerate(bones)}

		for i, bone in enumerate(bones):
			slice = armature[i*SIZEOF:(i*SIZEOF)+SIZEOF]

			local_matrix = bone.matrix_local
			location = YMP.AXIS_FIX_INV @ local_matrix.to_translation()
			rotation = local_matrix.to_euler('ZYX')

			name = bone.name.encode('shift_jis', errors='ignore')
			slice[0:16] = name[:16].ljust(16, b'\x00')

			if bone.parent is None:
				parent = NO_PARENT
			else:
				parent = bone_index[bone.parent]

			slice[48:52] = parent.to_bytes(4, 'little', signed=True)

			v1 = slice.cast('f')
			v1[4]  = location.x
			v1[5]  = location.y
			v1[6]  = location.z
			v1[7]  = 1.0
			v1[8]  = rotation.x
			v1[9]  = rotation.y
			v1[10] = rotation.z
			v1[11] = 0.0

		return armature


	def write_collections(self):
		SIZEOF = 32
		COUNT = len(self.obj_groups)
		size_to_allocate = SIZEOF * COUNT
		col = mem_alloc(size_to_allocate)
		for i, collection in enumerate(self.obj_groups):
			slice = col[i*SIZEOF:(i*SIZEOF)+SIZEOF]
			name = collection.name
			slice[0:16] = name.encode('shift_jis', errors='ignore')[0:16].ljust(16, b'\x00')
			v1 = slice.cast('i')
			v1[4] = 1 # ?
			objects = collection.objects
			objs = []
			obj_count = 0
			for obj in objects:
				if obj.type == 'MESH':
					objs.append(obj)
				elif obj.type in {'CURVES', 'CURVE'}:
					warnings.warn('Please convert non-mesh objects into meshes. This mesh will be skipped', UserWarning, source=obj)
					continue
				else:
					continue
			obj_count = len(objs)
			del objs, objects
			assert obj_count > 0
			v1[6] = obj_count & 0xFFFFFFFF
		return col

	def start(self):
		objectss = []
		for collection in self.obj_groups:
			objects = collection.objects
			iv = self.write_subobject(objects)
			objectss.append(iv)
		arm = self.write_armature()
		col = self.write_collections()
		with open(self.path, 'wb') as f:
			for obj in objectss:
				f.write(obj)
			f.write(arm)
			f.write(col)
	def write_subobject(self, objects: bpy.types.CollectionObjects):
		SIZEOF = 64
		COUNT = len(objects)
		size_to_allocate = SIZEOF * COUNT
		object = mem_alloc(size_to_allocate)
		for i, obj in enumerate(objects):
			if obj.type != 'MESH':
				continue
			slice = object[i*SIZEOF:(i*SIZEOF)+SIZEOF]
			v1 = slice.cast('I')
			v2 = slice.cast('f')
			# Get bounding box corners in world space
			bb_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

			min_v = Vector((
				min(v.x for v in bb_world),
				min(v.y for v in bb_world),
				min(v.z for v in bb_world),
			))

			max_v = Vector((
				max(v.x for v in bb_world),
				max(v.y for v in bb_world),
				max(v.z for v in bb_world),
			))

			C, R = write_sphere(min_v, max_v)
			centre = Vector(C)
			v2[12] = centre[0]
			v2[13] = centre[1]
			v2[14] = centre[2]
			v2[15] = R
		return object