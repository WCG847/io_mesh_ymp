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
from bpy_extras.io_utils import ImportHelper
from bpy.props import FloatProperty, StringProperty
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

	filename_ext = ".ymp"

	filter_glob: StringProperty(
		default="*.ymp",
		options={'HIDDEN'}
	)

	scale: FloatProperty(
		name="Scale",
		min=0.0,
		max=16.0,
		subtype='FACTOR'
	)

	def execute(self, context):
		if self.filepath:
			with open(self.filepath, 'rb') as f:
				assert f.read(4) == b'YOBJ'
				file = memoryview(bytearray(f.read([f.seek(4), int.from_bytes(f.read(4), 'little')][1])))
				m = SkinModel(file, self.scale)
			m.start()
		return {'FINISHED'}
def menu_func_import(self, context):
    self.layout.operator(IMPORT_YMP.bl_idname, text="YMP (.ymp)")

def register():
    bpy.utils.register_class(YMP_PROPS)
    bpy.utils.register_class(IMPORT_YMP)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_YMP)
    bpy.utils.unregister_class(YMP_PROPS)
