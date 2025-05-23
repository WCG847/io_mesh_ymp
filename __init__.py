bl_info = {
	"name": "YMP Skin Model Importer",
	"blender": (3, 0, 0),
	"category": "Import-Export",
	"author": "PPTM",
	"version": (1, 0, 0),
	"description": "Import and visualize YMP skin model data in Blender"
}

import sys, os

print("Addon loaded from:", os.path.abspath(__file__))
print("sys.path:")
for p in sys.path:
	print(" -", p)

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from .Import.cskinmodel import CSkinModel


class IMPORT_OT_ymp_model(Operator, ImportHelper):
	bl_idname = "import_scene.ymp_model"
	bl_label = "Import YMP Skin Model"
	bl_options = {'PRESET', 'UNDO'}

	filename_ext = ".ymp"
	filter_glob: StringProperty(
		default="*.ymp",
		options={'HIDDEN'}
	)

	def execute(self, context):
		with open(self.filepath, 'rb') as file:
			model = CSkinModel(file)
			model.ToBpy()
		return {'FINISHED'}


def menu_func_import(self, context):
	self.layout.operator(IMPORT_OT_ymp_model.bl_idname, text="YMP Skin Model (.ymp)")


def register():
	bpy.utils.register_class(IMPORT_OT_ymp_model)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
	bpy.utils.unregister_class(IMPORT_OT_ymp_model)
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
	register()