from io import BytesIO
from struct import Struct, pack
from typing import Iterable

import bpy
from mathutils import Color


class YMXEN:
	header = Struct('>4i')
	table = Struct('>4i')
	subobject = Struct('>3i20i7i16s7if3f')
	NULL = -1
	material = Struct('>16s2h')
	FVF = Struct('>3f3fi')
	UV = Struct('>ff')
	batch_header = Struct('>III')
	collections = Struct('>16s4i')
	def __init__(self, collections: Iterable[bpy.types.Collection], armature: bpy.types.Object):
		self.cols = collections
		self.armature = armature
		self.structs: list[BytesIO] = []

	def write(self):
		self.textures: list[str] = []
		self.write_collections()

	def write_collections(self):
		SIZEOF = self.collections.size * len(self.cols)
		field = memoryview(bytearray(SIZEOF))
		for i, parent in enumerate(self.cols):
			got = field[i*self.collections.size:(i*self.collections.size)+self.collections.size]
			counter = 0
			for child in parent.objects:
				if child.type == 'MESH':
					counter += 1
			name = parent.name.ljust(16, '\x00')[:16].encode('shift_jis', 'ignore')
			YMXEN.collections.pack_into(got, 0, name, True, 0, counter, 0)
		return field

	def write_fvf(self, positions: bpy.types.MeshVertices, colours: bpy.types.ByteColorAttribute):
		d = BytesIO()
		assert colours.domain == 'POINT', "Vertex Colours not found"
		for vert, colour in zip(positions, colours.data):
			d.write(pack('>3f', *vert.co))
			d.write(pack('>3f', *vert.normal))
			RGBA = colour.color
			A = int(RGBA[3] * 255 + 0.5)
			R = int(RGBA[0] * 255 + 0.5)
			G = int(RGBA[1] * 255 + 0.5)
			B = int(RGBA[2] * 255 + 0.5)
			d.write(pack('>4B', A, R, G, B))

	def write_materials(self, mat: bpy.types.Material):
		d = BytesIO()
		d.write(YMXEN.material.pack(b'g_f4MatAmbCol', 13, 36))
		d.write(pack('>4f', *bpy.context.scene.world.node_tree.nodes["Background"].inputs["Color"].default_value))
		FX = None
		for shader in mat.node_tree.nodes:
			if shader.type == 'BSDF_PRINCIPLED':
				YUKES = b'yBumpMap'
				FX = shader
				break
		if not FX:
			raise ValueError('No shader')
		print('Converting BSDF to D3DMATERIAL9...')
		d.write(YMXEN.material.pack(b'g_bUseRefRegMap', 16, 24))
		d.write(b'\x00\x00\x00\x00') # False
		for input in FX.inputs:
			match input.name:
				case 'Base Color':
					if input.is_linked:
						if (from_node := input.links[0].from_node).bl_idname == "ShaderNodeTexImage":
							from_node: bpy.types.ShaderNodeTexImage
							tex = from_node.image
							if tex not in self.textures:
								self.textures.append(tex)
							id = self.textures.index(tex)
							d.write(YMXEN.material.pack(b'texDiffuse', 15, 24))
							d.write(pack('>i', id))

					else:
						RGBA = tuple(input.default_value)
						d.write(YMXEN.material.pack(b'g_f4MatDifCol', 13, 36))
						d.write(pack('>4f', *RGBA))
				case 'Roughness':
					assert not input.is_linked
					p = max(0, min(128, round(128 * (1.0 - input.default_value))))
					
					d.write(YMXEN.material.pack(b'g_iSpecularPow', 5, 24))
					d.write(pack('>i', p))

				case 'Specular Tint':
					d.write(YMXEN.material.pack(b'g_f4SpecularCol', 13, 36))
					d.write(pack('>4f', *input.default_value))
		return d.getvalue()
