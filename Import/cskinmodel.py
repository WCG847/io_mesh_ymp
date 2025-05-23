from io import BytesIO
from typing import BinaryIO
from struct import unpack, pack
from mathutils import Matrix, Vector, Quaternion
import re
import bpy
from .csubobject import CSubObject

class CSkinModel:
	def __init__(self, ympSkinModel: BinaryIO):
		if ympSkinModel is None:
			return
		ympSkinModel.seek(4)
		size = unpack('<I', ympSkinModel.read(4))[0]
		ympSkinModel.seek(8)
		self.YMP = BytesIO(ympSkinModel.read(size))
		ympSkinModel.close()
		ympSkinModel = None
		del ympSkinModel
		self.Create()

	def _ympCleanBoneName(self) -> None:
		self.YMP.seek(0x20)
		ympBoneOffset = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(0x14)
		ympBoneCount = unpack('<I', self.YMP.read(4))[0]
		boneSize = ((ympBoneCount << 2) + ympBoneCount) << 4
		self.YMP.seek(boneSize + ympBoneOffset)
		if self.YMP.tell() == ympBoneOffset:
			return False
		for i in range(ympBoneCount):
			rawname = unpack('16s', self.YMP.read(16))[0]
			name = re.sub(r'[^ -~]', '', rawname.decode('latin1', errors='ignore'))
			self.YMP.seek(-16, 1)
			self.YMP.write(pack('16s', name.encode('latin1')))
			self.YMP.seek(0x50, 1)
		return

	def Create(self):
		self._ympCleanBoneName()
		self.YMP.seek(0x14)
		ympBoneCount = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(0x20)
		ympBoneOffset = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(ympBoneOffset)
		self.BoneEntries = []
		for i in range(ympBoneCount):
			print(f"UP {i} with bone count {ympBoneCount}")
			name = unpack('16s', self.YMP.read(16))[0].decode('latin1').rstrip('\x00')
			translation = unpack('<4f', self.YMP.read(4 * 4))
			rotation = unpack('<4f', self.YMP.read(4 * 4))
			parentID = unpack('<I', self.YMP.read(4))[0]
			tx, ty, tz, _ = translation
			rx, ry, rz, rw = rotation
			trans_vec = Vector((tx, ty, tz))
			quat = Quaternion((rw, rx, ry, rz))
			matrix = Matrix.Translation(trans_vec) @ quat.to_matrix().to_4x4()
			self.YMP.seek(0xC, 1)
			matrix_rows = [unpack('<4f', self.YMP.read(16)) for _ in range(4)]
			restpose_matrix = Matrix(matrix_rows)
			self.BoneEntries.append((name, translation, rotation, parentID, matrix, restpose_matrix))
		self.YMP.seek(0x18)
		ympTexCount = unpack('<I', self.YMP.read(4))[0]
		print(f"got {ympTexCount}")
		self.YMP.seek(0x24)
		ympTexOffset = unpack('<I', self.YMP.read(4))[0]
		print(f"got {ympTexOffset}")
		self.YMP.seek(ympTexOffset)
		self.GetTexture(ympTexCount)
		self.YMP.seek(0x1C)
		ympSubObjectPointer = unpack('<I', self.YMP.read(4))[0]
		print(f"got {ympSubObjectPointer}")
		self.YMP.seek(16)
		ympSubObjectCount = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(ympSubObjectPointer)
		print(f"at {self.YMP.tell()}")
		sub = CSubObject(self.BoneEntries)
		sub.Create(self.YMP, ympSubObjectCount)
		self.SubObjectEntries = sub.SubObjectEntries


	def GetTexture(self, count):
		self.Entries = []
		for i in range(count):
			print(f"at {self.YMP.tell()}")
			rawname = unpack('16s', self.YMP.read(16))[0]
			name = rawname.decode('latin1', errors='ignore').split('\x00', 1)[0]
			self.Entries.append(name)

	def ToBpy(self):
		arm_data = bpy.data.armatures.new("CSkinModel_Armature")
		arm_object = bpy.data.objects.new("CSkinModel_Armature", arm_data)
		bpy.context.collection.objects.link(arm_object)
		bpy.context.view_layer.objects.active = arm_object
		bpy.ops.object.mode_set(mode='EDIT')

		bones_map = {}
		for idx, (name, _, _, parentID, bone_matrix, _) in enumerate(self.BoneEntries):
			bone = arm_data.edit_bones.new(name)
			bone.head = Vector((0, 0, 0))
			bone.tail = Vector((0, 0.1, 0))
			bone.matrix = bone_matrix
			bones_map[idx] = bone

		for idx, (_, _, _, parentID, _, _) in enumerate(self.BoneEntries):
			if parentID != 0xFFFFFFFF:
				bones_map[idx].parent = bones_map[parentID]

		bpy.ops.object.mode_set(mode='OBJECT')

		for i, sub in enumerate(self.SubObjectEntries):
			mesh_data = bpy.data.meshes.new(f"SubMesh_{i}")
			mesh_obj = bpy.data.objects.new(f"SubMesh_{i}", mesh_data)
			bpy.context.collection.objects.link(mesh_obj)
			vertices = [v.to_tuple() for v in sub['vertex_positions']]
			faces = [(i, i + 1, i + 2) for i in range(0, len(vertices) - 2, 3)]
			mesh_data.from_pydata(vertices, [], faces)
			mesh_data.update()
			for boneID, _ in enumerate(self.BoneEntries):
				mesh_obj.vertex_groups.new(name=self.BoneEntries[boneID][0])
			for idx, (w1, w2, w3) in enumerate(sub['weights']):
				bones = sub['params'][0][-3:]
				weights = [w1, w2, w3]
				for b_idx, weight in zip(bones, weights):
					try:
						mesh_obj.vertex_groups[self.BoneEntries[b_idx][0]].add([idx], weight, 'REPLACE')
					except IndexError:
						pass
			mod = mesh_obj.modifiers.new(name="ArmatureMod", type='ARMATURE')
			mod.object = arm_object
			mesh_obj.parent = arm_object

	def Release(self):
		if self.YMP is None:
			return True
		else:
			self.YMP.close()
			self.YMP = None
			del self.YMP
