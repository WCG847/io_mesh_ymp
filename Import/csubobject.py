from io import BytesIO
from typing import BinaryIO
from struct import unpack
from mathutils import Matrix, Vector, Quaternion

class CSubObject:
	def __init__(self, bone_entries):
		self.BoneEntries = bone_entries
		self.SubObjectEntries = []

	def Create(self, file: BinaryIO, count: int):

		if file.tell() == 0:
			return False

		for i in range(count):
			entry = {
				'params': [],
				'vertex_positions': [],
				'normals': [],
				'weights': [],
				'st_entries': [],
				'vertex_colors': [],
				'bounding_sphere_matrix': None
			}

			# Subobject metadata
			paramCount, STQCount, paramPointer, STQPointer, _, vertexGroupCount, \
			sectInfoPointer, vertexColourPTR, totalVertices, boneWeightCount, \
			mainVertexCount, _ = unpack('<12I', file.read(12 * 4))

			CentreX, CentreY, CentreZ, Radius = unpack("<4f", file.read(4 * 4))
			scale_matrix = Matrix.Scale(Radius, 4)
			translation_matrix = Matrix.Translation(Vector((CentreX, CentreY, CentreZ)))
			entry['bounding_sphere_matrix'] = translation_matrix @ scale_matrix

			# Parameters (bone-affected groups)
			file.seek(paramPointer)
			for _ in range(paramCount):
				verticesAffected, boneIndicesCount, vertexPosOffset, vertexNormOffset, \
				BoneIndex1, BoneIndex2, BoneIndex3 = unpack('<7I', file.read(28))

				entry['params'].append((verticesAffected, boneIndicesCount, vertexPosOffset,
										vertexNormOffset, BoneIndex1, BoneIndex2, BoneIndex3))

				bones = [BoneIndex1, BoneIndex2, BoneIndex3][:boneIndicesCount]
				# Filter out invalid bone IDs (e.g., -1 == 0xFFFFFFFF)
				bones = [b for b in bones if 0 <= b < len(self.BoneEntries)]

				# If no valid bones remain, skip vertex group
				if not bones:
					print(f"[WARN] All bones invalid for param group; skipping.")
					continue

				# Equal weights for valid bones
				weights = [1.0 / len(bones)] * len(bones)

				# Positions
				file.seek(vertexPosOffset)
				for _ in range(verticesAffected):
					pos = Vector(unpack('<4f', file.read(16)))
					weighted_pos = Vector((0.0, 0.0, 0.0))

					for b_idx, bone_id in enumerate(bones):
						if not (0 <= bone_id < len(self.BoneEntries)):
							print(f"[ERROR] Bone ID {bone_id} out of bounds — skipping transform.")
							continue
						_, _, _, _, bone_matrix, restpose = self.BoneEntries[bone_id]
						inv_bind = restpose.inverted()
						final_matrix = bone_matrix @ inv_bind
						weighted_pos += (final_matrix @ pos.to_3d()) * weights[b_idx]


					entry['vertex_positions'].append(weighted_pos)

				# Normals
				file.seek(vertexNormOffset)
				for _ in range(verticesAffected):
					normal = Vector(unpack('<4f', file.read(16)))
					transformed_normal = Vector((0.0, 0.0, 0.0))
					for b_idx, bone_id in enumerate(bones):
						if not (0 <= bone_id < len(self.BoneEntries)):
							print(f"[ERROR] Invalid bone ID {bone_id} during normal transform")
							continue
						_, _, _, _, bone_matrix, restpose = self.BoneEntries[bone_id]
						inv_bind = restpose.inverted()
						final_matrix = bone_matrix @ inv_bind
						n = final_matrix.to_3x3() @ normal.to_3d()
						transformed_normal += n.normalized() * weights[b_idx]

					entry['normals'].append(transformed_normal.normalized())

			# STQ data
			file.seek(STQPointer)
			for _ in range(STQCount):
				st_data = unpack('<8f', file.read(32))  # 4 ST pairs
				STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))

				ST_Entries = [
					(st_data[0], st_data[1]),
					(st_data[2], st_data[3]),
					(st_data[4], st_data[5]),
				]

				if GroupInterpretation == 7 and marker == 0:
					st_data2 = unpack('<8f', file.read(32))
					STGroupID, GroupInterpretation, BatchID, marker = unpack('<4I', file.read(16))
					ST_Entries += [
						(st_data2[0], st_data2[1]),
						(st_data2[2], st_data2[3]),
						(st_data2[4], st_data2[5]),
					]

				entry['st_entries'].append(ST_Entries)

				file.seek(0x60, 1)  # Skip unknowns
				_, _, faceCount = unpack('<3H', file.read(6))
				startFaceGroup, _ = unpack('<2I', file.read(8))

				file.seek(startFaceGroup)
				for _ in range(faceCount):
					file.seek(8, 1)
					boneWeightGroupCount, boneWeightGroupOffset = unpack('<2I', file.read(8))
					cp = file.tell()
					file.seek(boneWeightGroupOffset)
					for _ in range(boneWeightGroupCount):
						weight1, weight2, weight3 = unpack('<3f', file.read(12))
						vertexindex = unpack('<I', file.read(4))[0]
						while len(entry['weights']) <= vertexindex:
							entry['weights'].append((0.0, 0.0, 0.0))
						entry['weights'][vertexindex] = (weight1, weight2, weight3)
					file.seek(cp)

			# Per-vertex bone weights
			for _ in range(boneWeightCount):
				file.seek(0x0C, 1)
				memID = unpack('<H', file.read(2))[0]
				vertexCount = unpack('B', file.read(1))[0]
				file.seek(1, 1)
				for _ in range(vertexCount):
					file.seek(0x10, 1)
					weight1, weight2, weight3 = unpack('<3f', file.read(12))
					vertexindex = unpack('<I', file.read(4))[0]
					while len(entry['weights']) <= vertexindex:
						entry['weights'].append((0.0, 0.0, 0.0))
					entry['weights'][vertexindex] = (weight1, weight2, weight3)

			# Vertex colors
			if vertexColourPTR != 0 and vertexColourPTR != STQPointer:
				file.seek(vertexColourPTR)
				while file.tell() < STQPointer:
					file.seek(0x0C, 1)
					memID = unpack('<H', file.read(2))[0]
					vertexCount = unpack('B', file.read(1))[0]
					file.seek(1, 1)
					for _ in range(vertexCount):
						vec4 = unpack('<4f', file.read(16))
						entry['vertex_colors'].append(vec4)

			self.SubObjectEntries.append(entry)