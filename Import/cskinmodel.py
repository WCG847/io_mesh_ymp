from io import BytesIO
from typing import BinaryIO
from struct import unpack, pack
from mathutils import Matrix, Vector, Quaternion
import re
from csubobject import CSubObject

class CSkinModel:
	def __init__(self, ympSkinModel:BinaryIO):
		if ympSkinModel is None:
			return
		ympSkinModel.seek(4)
		size = unpack('<I', ympSkinModel.read(4))[0]
		ympSkinModel.seek(8)
		self.YMP = BytesIO(ympSkinModel.read(size)) # we dont need to decode POF0 relocation footer for importing.
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
		EOB = self.YMP.tell() # End Of Bone
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
			name = unpack('16s', self.YMP.read(16))[0].decode('latin1').rstrip('\x00')

			translation = unpack('<4f', self.YMP.read(4 * 4))
			rotation = unpack('<4f', self.YMP.read(4 * 4))
			parentID = unpack('<I', self.YMP.read(4))[0]
			if parentID == 0xFFFFFFFF:
				print('NO PARENT NEEDED.')

			tx, ty, tz, _ = translation
			rx, ry, rz, rw = rotation

			trans_vec = Vector((tx, ty, tz))
			quat = Quaternion((rw, rx, ry, rz))  # Blender expects WXYZ

			matrix = Matrix.Translation(trans_vec) @ quat.to_matrix().to_4x4()

			print(f"Bone: {name}, Matrix:\n{matrix}")
			self.BoneEntries.append((name, translation, rotation, parentID, matrix))

			self.YMP.seek(0x1C, 1)

		self.YMP.seek(0x18)
		ympTexCount = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(0x22)
		ympTexOffset = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(ympTexOffset)
		self.GetTexture(ympTexCount)
		self.YMP.seek(0x1C)
		ympSubObjectPointer = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(16)
		ympSubObjectCount = unpack('<I', self.YMP.read(4))[0]
		self.YMP.seek(ympSubObjectPointer)
		CSubObject().Create(self.YMP, ympSubObjectCount)

	def GetTexture(self, count):
		self.Entries = []
		for i in range(count):
			rawname = unpack('16s', self.YMP.read(16))[0]
			name = rawname.decode('latin1', errors='ignore').split('\x00', 1)[0]
			print(f"Got {name}.tga")
			self.Entries.append(name)
	def Release(self):
		if self.YMP is None:
			return True
		else:
			self.YMP.close()
			self.YMP = None
			del self.YMP







