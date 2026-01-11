bl_info = {
	"name": "YMP I/O",
	"author": "WCG847",
	"version": (1, 0, 0),
	"blender": (5, 0, 0),
	"location": "File/Import & File/Export",
	"description": "Import export YMP",
	"warning": "",
	"doc_url": "",
	"tracker_url": "",
	"category": "Import-Export",
}

import bpy
from bpy.types import AddonPreferences, Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import FloatProperty, StringProperty
from bpy.props import CollectionProperty
from bpy.types import OperatorFileListElement

from .src.ps2.Import.skinmodel import SkinModel

class YMP_PROPS(AddonPreferences):
	bl_idname = __name__
	tex_path: StringProperty(name='textures', subtype='DIR_PATH', maxlen=260)

	def draw(self, context: bpy.types.Context):
		layout = self.layout
		layout.prop(self, 'tex_path')


class IMPORT_YMP(Operator, ImportHelper):
	bl_idname = "import_scene.ymp"
	bl_label = "Import YMP"
	bl_description = "Imports Yuke's Models"

	filename_ext = ".ymp"

	filter_glob: StringProperty(
		default="*.ymp;*.yobj",
		options={'HIDDEN'}
	)
	use_filter_folder = True
	use_filter = True

	files: CollectionProperty(
		name="File Path",
		type=OperatorFileListElement
	)

	directory: StringProperty(
		subtype='DIR_PATH'
	)

	scale: FloatProperty(
		name="Scale",
		min=0.0,
		max=16.0,
		default=1.0,
		subtype='FACTOR'
	)

	def execute(self, context):
		for file_elem in self.files:
			full_path = bpy.path.abspath(
				self.directory + file_elem.name
			)

			with open(full_path, 'rb') as f:
				if f.read(4) != b'YOBJ':
					self.report({'WARNING'}, f"Skipping {file_elem.name}")
					continue

				size = int.from_bytes(f.read(4), 'little')
				file = memoryview(bytearray(f.read(size)))

				m = SkinModel(file, self.scale)
				m.start()

		return {'FINISHED'}

class EXPORT_YMP(Operator, ExportHelper):
	bl_idname = "export_scene.ymp"
	bl_label = "Export YMP"
	bl_description = "Exports Yuke's Models"

	filename_ext = ".ymp"

	use_filter_folder = True
	use_filter = True
	def execute(self, context):
		pass

def menu_func_import(self, context):
	self.layout.operator(IMPORT_YMP.bl_idname, text="YMP (.ymp)")

def menu_func_export(self, context):
	self.layout.operator(EXPORT_YMP.bl_idname, text="YMP (.ymp)")

def register():
	bpy.utils.register_class(YMP_PROPS)
	bpy.utils.register_class(IMPORT_YMP)
	bpy.utils.register_class(EXPORT_YMP)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	bpy.utils.unregister_class(IMPORT_YMP)
	bpy.utils.unregister_class(EXPORT_YMP)
	bpy.utils.unregister_class(YMP_PROPS)


