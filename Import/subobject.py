from struct import unpack
from cskinmodel import CSkinModel
import bpy
from enum import IntEnum


class UnpackMode(IntEnum):
	'''According to PS2Sdk'''
	P2_UNPACK_S_32 = 0x00
	P2_UNPACK_S_16 = 0x01
	P2_UNPACK_S_8 = 0x02
	P2_UNPACK_V2_32 = 0x04
	P2_UNPACK_V2_16 = 0x05
	P2_UNPACK_V2_8 = 0x06
	P2_UNPACK_V3_32 = 0x08
	P2_UNPACK_V3_16 = 0x09
	P2_UNPACK_V3_8 = 0x0A
	P2_UNPACK_V4_32 = 0x0C
	P2_UNPACK_V4_16 = 0x0D
	P2_UNPACK_V4_8 = 0x0E
	P2_UNPACK_V4_5 = 0x0F


class CSubObject(CSkinModel):
	def Create(self, count, file):
		self.file = file
		for i in range(count):
			self.col = bpy.data.collections.new(f"object{i:02}")
			bpy.context.collection.children.link(self.col)
			(
				vertexskincount,
				uvcount,
				vertexskinpointer,
				uvpointer,
				colourtablecount,
				vgcount,
				colourtableptr,
				colourptr,
				combinedvertices,
				colourcount,
				indiviualvertexcount,
				_,
			) = unpack("<12I", self.file.read(4 * 12))
			centre = unpack("<3f", self.file.read(12))
			radius = unpack("<f", self.file.read(4))[0]
			bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=centre)
			bounding_obj = bpy.context.active_object
			self.col.objects.link(bounding_obj)
			bounding_obj.display_type = "WIRE"
			bounding_obj.hide_select = True
			mesh = bpy.data.meshes.new(f"m_{i}")
			self.obj = bpy.data.objects.new(f"obj{i}", mesh)
			self.col.objects.link(self.obj)
			self.file.seek(colourtableptr)
			vertexposptr = unpack("<I", self.file.read(4))[0]
			self.file.seek(vertexposptr + 0x0C)
			self.vertices, self.normals = self.VertexParser()


	def VertexParser(self):
		vifcode = unpack("<I", self.file.read(4))[0]
		immediate = vifcode & 0x0000FFFF
		num = (vifcode & 0x00FF0000) >> 16
		cmd = (vifcode & 0xFF000000) >> 24

		if num == 0:
			num = 256
			print(f'Got {num} vertices')

		mode = cmd & 0x0F
		if mode == UnpackMode.P2_UNPACK_V4_32:
			print(f'Mode is Vec4')
		else:
			raise ValueError(f"Can't identify the mode")

		if immediate == 0:
			print(f'Parsing {num} positions')
			raw_data = self.file.read(num * 16)
			base = unpack("<4f", raw_data[0:16])
			print(f'Base vector: {base}')

			vertices = []
			for i in range(1, num):
				offset = i * 16
				vec = unpack("<4f", raw_data[offset:offset+16])
				resolved = tuple(base[j] + vec[j] for j in range(3))  # only x, y, z
				vertices.append(resolved)

			print(f'Resolved {len(vertices)} vertex positions')
			self.file.seek(0x0C, 1)
			vifcode = unpack("<I", self.file.read(4))[0]
			immediate = vifcode & 0x0000FFFF
			num = (vifcode & 0x00FF0000) >> 16
			cmd = (vifcode & 0xFF000000) >> 24
			if immediate == 0xA0:
				print(f'Parsing {num} normals')
				raw_data = self.file.read(num * 16)
				base = unpack("<4f", raw_data[0:16])
				print(f'Base vector: {base}')

				normals = []
				for i in range(1, num):
					offset = i * 16
					vec = unpack("<4f", raw_data[offset:offset+16])
					resolved = tuple(base[j] + vec[j] for j in range(3))  # only x, y, z
					normals.append(resolved)

				print(f'Resolved {len(vertices)} vertex normals')

			return vertices, normals