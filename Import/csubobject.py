from io import BytesIO
from typing import BinaryIO
from struct import unpack, pack
from mathutils import Matrix, Vector, Quaternion
from cskinmodel import CSkinModel

class CSubObject(CSkinModel):
	def Create(self, file: BinaryIO, count: int):
		self.SubObjectEntries = []

		if file.tell() == 0:
			return False

		for i in range(count):
			entry = {
				'params': [],
				'vertex_positions': [],
				'weights': [],
				'st_entries': [],
				'vertex_colors': [],
				'bounding_sphere_matrix': None
			}

			# Read basic subobject data
			paramCount, STQCount, paramPointer, STQPointer, _, vertexGroupCount, \
			sectInfoPointer, vertexColourPTR, totalVertices, boneWeightCount, \
			mainVertexCount, _ = unpack('<12I', file.read(12 * 4))

			CentreX, CentreY, CentreZ, Radius = unpack("<4f", file.read(4 * 4))
			scale_matrix = Matrix.Scale(Radius, 4)
			translation_matrix = Matrix.Translation(Vector((CentreX, CentreY, CentreZ)))
			entry['bounding_sphere_matrix'] = translation_matrix @ scale_matrix

			# Parse parameter data
			file.seek(paramPointer)
			for j in range(paramCount):
				verticesAffected, boneIndicesCount, vertexPosOffset, vertexNormOffset, \
				BoneIndex1, BoneIndex2, BoneIndex3 = unpack('<7I', file.read(7 * 4))

				entry['params'].append((verticesAffected, boneIndicesCount, vertexPosOffset, vertexNormOffset,
										BoneIndex1, BoneIndex2, BoneIndex3))

				cp = file.tell()
				file.seek(vertexPosOffset)
				for k in range(verticesAffected):
					pos = Vector(unpack('<4f', file.read(16)))  # XYZW delta
					weighted_pos = Vector((0.0, 0.0, 0.0))

					bones = [BoneIndex1, BoneIndex2, BoneIndex3][:boneIndicesCount]

					# Dummy weights for now, corrected later
					weights = [1.0 / boneIndicesCount] * boneIndicesCount

					for b_idx, bone_id in enumerate(bones):
						bone_name, _, _, _, bone_matrix, restpose = self.BoneEntries[bone_id]
						inv_bind = restpose.inverted()
						final_matrix = bone_matrix @ inv_bind
						weighted_pos += (final_matrix @ pos.to_3d()) * weights[b_idx]

					entry['vertex_positions'].append(weighted_pos)

				file.seek(cp)

			# Parse STQ entries
			file.seek(STQPointer)
			for l in range(STQCount):
				st_data = unpack('<8f', file.read(32))  # 4 ST pairs
				STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))

				ST_Entries = [
					(st_data[0], st_data[1]),
					(st_data[2], st_data[3]),
					(st_data[4], st_data[5]),
				]

				# Check if extended STs needed
				if GroupInterpretation == 7 and l < STQCount - 1 and marker == 0:
					st_data2 = unpack('<8f', file.read(32))
					STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))
					ST_Entries += [
						(st_data2[0], st_data2[1]),
						(st_data2[2], st_data2[3]),
						(st_data2[4], st_data2[5]),
					]

				entry['st_entries'].append(ST_Entries)

				file.seek(0x60, 1)  # skip unknowns

				groupCount, PS2Ram, faceCount = unpack('<3H', file.read(6))
				startFaceGroup, startBoneWeight = unpack('<2I', file.read(8))

				# Bone weight section
				file.seek(startFaceGroup)
				for m in range(faceCount):
					file.seek(8, 1)
					boneWeightGroupCount, boneWeightGroupOffset = unpack('<2I', file.read(8))
					cp = file.tell()
					file.seek(boneWeightGroupOffset)
					for n in range(boneWeightGroupCount):
						weight1, weight2, weight3 = unpack('<3f', file.read(12))
						vertexindex = unpack('<I', file.read(4))[0]
						if vertexindex < len(entry['weights']):
							entry['weights'][vertexindex] = (weight1, weight2, weight3)
						else:
							entry['weights'].append((weight1, weight2, weight3))
					file.seek(cp)

			# Additional bone weights per group
			for q in range(boneWeightCount):
				file.seek(0x0C, 1)
				memID = unpack('<H', file.read(2))[0]
				vertexCount = unpack('B', file.read(1))[0]
				file.seek(1, 1)
				for r in range(vertexCount):
					file.seek(0x10, 1)
					weight1, weight2, weight3 = unpack('<3f', file.read(12))
					vertexindex = unpack('<I', file.read(4))[0]
					if vertexindex < len(entry['weights']):
						entry['weights'][vertexindex] = (weight1, weight2, weight3)
					else:
						entry['weights'].append((weight1, weight2, weight3))

			# Vertex colors
			if vertexColourPTR != 0 and vertexColourPTR != STQPointer:
				file.seek(vertexColourPTR)
				for o in range(STQPointer - vertexColourPTR):
					file.seek(0x0C, 1)
					memID = unpack('<H', file.read(2))[0]
					vertexCount = unpack('B', file.read(1))[0]
					file.seek(1, 1)
					for p in range(vertexCount):
						vec4 = unpack('<4f', file.read(16))
						entry['vertex_colors'].append(vec4)

			self.SubObjectEntries.append(entry)
