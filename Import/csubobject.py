from io import BytesIO
from typing import BinaryIO
from struct import unpack, pack
from mathutils import Matrix, Vector, Quaternion
from cskinmodel import CSkinModel

class CSubObject(CSkinModel):
	def Create(self, file, count):
		SubObjectEntries = []
		if file.tell() == 0:
			return False
		for i in range(count):
			paramCount, STQCount, paramPointer, STQPointer, _, vertexGroupCount, sectInfoPointer, vertexColourPTR, totalVertices, boneWeightCount, mainVertexCount, _ = unpack('<12I', file.read(12 * 4))
			CentreX, CentreY, CentreZ, Radius = unpack("<4f", file.read(4 * 4))
			scale_matrix = Matrix.Scale(Radius, 4)
			translation_matrix = Matrix.Translation(Vector((CentreX, CentreY, CentreZ)))
			bounding_sphere_matrix = translation_matrix @ scale_matrix
			file.seek(paramPointer)
			for j in range(paramCount):
				params = []
				verticesAffected, boneIndicesCount, vertexPosOffset, vertexNormOffset, BoneIndex1, BoneIndex2, BoneIndex3 = unpack('<7I', file.read(7 * 4))
				params.append((verticesAffected, boneIndicesCount, vertexPosOffset, vertexNormOffset, BoneIndex1, BoneIndex2, BoneIndex3))
				cp = file.tell()
				file.seek(vertexPosOffset)
				vertex_positions = []
				for k in range(verticesAffected):
					pos = Vector(unpack('<4f', file.read(16)))  # XYZW delta
					weighted_pos = Vector((0.0, 0.0, 0.0))

					bones = [BoneIndex1, BoneIndex2, BoneIndex3][:boneIndicesCount]
					weights = [0.0] * boneIndicesCount  # need to get actual weights

					for b_idx, bone_id in enumerate(bones):
						bone_name, _, _, _, bone_matrix, restpose = self.BoneEntries[bone_id]
						inv_bind = restpose.inverted()
						final_matrix = bone_matrix @ inv_bind
						weighted_pos += (final_matrix @ pos.to_3d()) * weights[b_idx]

					vertex_positions.append(weighted_pos)
			self.YMP.seek(STQPointer)
			for l in range(STQCount - 1, -1, -1):
				st_data = unpack('<8f', file.read(32))  # 4 ST pairs
				STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))

				ST_Entries = [
					(st_data[0], st_data[1]),
					(st_data[2], st_data[3]),
					(st_data[4], st_data[5]),
				]

				if GroupInterpretation == 7 and l > 1 and marker == 0:
					st_data2 = unpack('<8f', file.read(32))
					STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))
					ST_Entries += [
						(st_data2[0], st_data2[1]),
						(st_data2[2], st_data2[3]),
						(st_data2[4], st_data2[5]),
					]

				file.seek(0x60, 1)
				groupCount, PS2Ram, faceCount = unpack('<3H', file.read(6))
				startFaceGroup, startBoneWeight = unpack('<2I', file.read(8))
				self.YMP.seek(startFaceGroup)
				for m in range(faceCount):
					file.seek(8, 1) # always 3 for both uint32s
					boneWeightGroupCount, boneWeightGroupOffset = unpack('<2I', file.read((2 * 4)))
					cp = file.tell()
					file.seek(boneWeightGroupOffset)
					for n in range(boneWeightGroupCount):
						weight1, weight2, weight3 = unpack('<3f', file.read((3 * 4)))
						vertexindex = unpack('<I', file.read(4))
					file.seek(cp)
				for q in range(boneWeightCount):
					file.seek(0x0C, 1)
					memID = unpack('<H', file.read(2))[0]
					vertexCount = unpack('B', file.read(1))[0]
					file.seek(1, 1)
					for r in range(vertexCount):
						file.seek(0x10, 1)
						weight1, weight2, weight3 = unpack('<3f', file.read((3 * 4)))
						vertexindex = unpack('<I', file.read(4))

				if vertexColourPTR != 0 or vertexColourPTR != STQPointer:
					file.seek(vertexColourPTR)
					for o in range((STQPointer - vertexColourPTR)):
						file.seek(0x0C, 1)
						memID = unpack('<H', file.read(2))[0]
						vertexCount = unpack('B', file.read(1))[0]
						file.seek(1, 1)
						for p in range(vertexCount):
							vec4 = unpack('<4f', file.read(4 * 4))





			


						

