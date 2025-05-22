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
				for k in range(verticesAffected):


