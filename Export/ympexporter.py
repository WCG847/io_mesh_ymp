import bpy
from struct import pack, pack_into
from bpy_extras.io_utils import ExportHelper
from io import BytesIO
from subobjectexporter import CSubObjectExporter

objexport = CSubObjectExporter()

class CYmpExporter(bpy.types.Operator, ExportHelper):
	bl_idname = "export_scene.ymp_exporter"
	bl_label = "Export .YMP Binary"
	filename_ext = ".ymp"

	def execute(self, context):
		pass

	def ExportHeader(self, context, name):
		self.pof0offsets = [0x1C, 0x20, 0x24, 0x28]
		try:
			file = open(name, 'wb+')
		except Exception:
			self.report({'ERROR'}, "FILE IS UNACCESSIBLE!!!")
			assert file, "FILE == NONE"
			raise IOError('Could not open file.')
		self.report({'INFO'}, "Opened File")
		file.write(b'\x00' * 72)
		print('wrote 72 bytes')
		file.seek(0)
		file.write(pack('4s', b'YOBJ'))
		print('wrote the YOBJ header at offset 0.')
		file.seek(8)
		ympSkinModel = BytesIO(file.read())
		ympSkinModel.seek(16)
		objectCount = len(bpy.data.objects) & 0xFFFFFFFF
		ympSkinModel.write(pack('<I', objectCount))
		boneCount = len(bpy.data.armatures) & 0xFFFFFFFF
		ympSkinModel.write(pack('<I', boneCount))
		texcount = len(bpy.data.textures) & 0xFFFFFFFF
		ympSkinModel.write(pack('<I', texcount))
		ympSkinModel.write(pack('<I', 0x40)) # just stick in 0x40
		ympSkinModel.seek(0x40)
		objexport.WriteHeader()