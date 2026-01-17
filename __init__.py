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
import os

from .src.ps2.Import.skinmodel import SkinModel
from .src.Xbox.Import.skinmodel import YMXEN_SkinModel
from .src.ps2.Export.ymp import YMP

class YMP_PROPS(AddonPreferences):
	bl_idname = __name__
	tex_path: StringProperty(name='textures', subtype='DIR_PATH', maxlen=260)

	def draw(self, context):
		layout = self.layout
		layout.prop(self, 'tex_path')

		if self.tex_path and not os.path.isdir(self.tex_path):
			layout.label(text="Path does not exist", icon='ERROR')



class IMPORT_YMP_PS2(Operator, ImportHelper):
	bl_idname = "import_scene.ymp_model_ps2"
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
				prefs = bpy.context.preferences.addons[__name__].preferences
				m.set_texture(prefs.tex_path)
				#m.build_materials()
				m.start()

		return {'FINISHED'}


class IMPORT_YMP_XBOX(Operator, ImportHelper):
	bl_idname = "import_scene.ymp_model_xbox"
	bl_label = "Import YMP"
	bl_description = "Imports Yuke's Models"

	filename_ext = ".ymxen"

	filter_glob: StringProperty(
		default="*.ymxen;*.jboy;*.yobj",
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
				if f.read(4)[::-1] != b'YOBJ':
					self.report({'WARNING'}, f"Skipping {file_elem.name}")
					continue

				size = int.from_bytes(f.read(4), 'big')
				file = memoryview(bytearray(f.read(size)))

				m = SkinModel(file, self.scale)
				m.set_texture()
				m.start()

		return {'FINISHED'}
class IMPORT_MT_ymp(bpy.types.Menu):
	bl_label = "Yuke's Model Properties"

	def draw(self, context):
		layout = self.layout
		layout.operator("import_scene.ymp_model_ps2", text="PlayStation 2 (.YMP, .YOBJ)")
		layout.operator("import_scene.ymp_model_xbox", text="Xbox 360 (.YMXEN, .JBOY)")


class EXPORT_YMP_PS2(Operator, ExportHelper):
	bl_idname = "export_scene.ymp_model_ps2"
	bl_label = "Export YMP (PS2)"
	bl_description = "Exports Yuke's Models"

	filename_ext = ".ymp"

	filter_glob: StringProperty(
		default="*.ymp",
		options={'HIDDEN'}
	)

	scale: FloatProperty(
		name="Scale",
		min=0.0,
		max=16.0,
		default=1.0,
		subtype='FACTOR'
	)

	def execute(self, context):
		path = self.filepath
		if not path:
			return {'CANCELLED'}
		c = bpy.context.scene.collection.objects
		arm = None
		for obj in c:
			if obj.type == 'ARMATURE':
				arm = obj
				break
		y  = YMP(arm, path, tuple(bpy.context.scene.collection.children))
		y.start()
		return {'FINISHED'}
def menu_func_export(self, context):
	self.layout.operator("export_scene.ymp_model_ps2", text="Yuke's Models (.YMP)")

def menu_func_import(self, context):
	self.layout.menu("IMPORT_MT_ymp", text="Yuke's Models")

def register():
	bpy.utils.register_class(YMP_PROPS)
	bpy.utils.register_class(IMPORT_YMP_PS2)
	bpy.utils.register_class(IMPORT_YMP_XBOX)
	bpy.utils.register_class(IMPORT_MT_ymp)

	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.utils.register_class(EXPORT_YMP_PS2)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)



def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

	bpy.utils.unregister_class(IMPORT_YMP_PS2)
	bpy.utils.unregister_class(IMPORT_YMP_XBOX)
	bpy.utils.unregister_class(IMPORT_MT_ymp)

	bpy.utils.unregister_class(YMP_PROPS)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
	bpy.utils.unregister_class(EXPORT_YMP_PS2)
