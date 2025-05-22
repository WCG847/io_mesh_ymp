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
			for l in range(STQCount):




