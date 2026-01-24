bl_info = {
	"name": "YMP I/O",
	"author": "WCG847",
	"version": (3, 0, 0),
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
from .src.XBOX.Import.skinmodel_ymxen import YMXEN_SkinModel


class IMPORT_YMP_PS2(Operator, ImportHelper):
	bl_idname = "import_scene.ymp_model_ps2"
	bl_label = "Import YMP"
	bl_description = "Imports Yuke's Models"

	filename_ext = ".ymp"

	filter_glob: StringProperty(default="*.ymp;*.yobj", options={"HIDDEN"})
	use_filter_folder = True
	use_filter = True

	files: CollectionProperty(name="File Path", type=OperatorFileListElement)

	directory: StringProperty(subtype="DIR_PATH")
	tex_path: StringProperty(name="textures", subtype="DIR_PATH", maxlen=260)
	scale: FloatProperty(name="Scale", min=0.0, max=16.0, default=1.0, subtype="FACTOR")

	def execute(self, context):
		for file_elem in self.files:
			full_path = bpy.path.abspath(self.directory + file_elem.name)

			with open(full_path, "rb") as f:
				if f.read(4) != b"YOBJ":
					self.report({"WARNING"}, f"Skipping {file_elem.name}")
					continue

				size = int.from_bytes(f.read(4), "little")
				file = memoryview(bytearray(f.read(size)))

				m = SkinModel(file, self.scale)
				if self.tex_path:
					m.set_texture(self.tex_path)
				# m.build_materials()
				m.start()

		return {"FINISHED"}


class IMPORT_YMP_XBOX(Operator, ImportHelper):
	bl_idname = "import_scene.ymp_model_xbox"
	bl_label = "Import YMP"
	bl_description = "Imports Yuke's Models"

	filename_ext = ".ymxen"

	filter_glob: StringProperty(
		default="*.ymp;*.yobj;*.jboy;*.ymxen", options={"HIDDEN"}
	)
	use_filter_folder = True
	use_filter = True

	files: CollectionProperty(name="File Path", type=OperatorFileListElement)

	directory: StringProperty(subtype="DIR_PATH")
	scale: FloatProperty(name="Scale", min=0.0, max=16.0, default=1.0, subtype="FACTOR")

	def execute(self, context):
		for file_elem in self.files:
			full_path = bpy.path.abspath(self.directory + file_elem.name)

			with open(full_path, "rb") as f:
				if f.read(4) != b"JBOY":
					self.report({"WARNING"}, f"Skipping {file_elem.name}")
					continue

				size = int.from_bytes(f.read(4), "big")
				file = memoryview(bytearray(f.read(size)))

			# Create model
			m = YMXEN_SkinModel(file, self.scale)

			# 1. Build texture slots from YMXEN table
			m.build_texture_slots()

			# 2. Collect all .tex files
			tex_filepacks = []
			tex_dir = self.directory

			for name in os.listdir(tex_dir):
				if name.lower().endswith(".tex"):
					tex_path = os.path.join(tex_dir, name)
					with open(tex_path, "rb") as tf:
						tex_filepacks.append(memoryview(tf.read()))

			# 3. Load all textures from all .tex files
			m.load_tex_files(tuple(tex_filepacks))

			# 4. Resolve YMXEN slots against loaded textures
			m.resolve_texture_slots()
			for name in os.listdir(tex_dir):
				name: str
				if name.lower().startswith("bane_muscle"):
					tex_path = os.path.join(tex_dir, name)
					m.apply_muscle_config(tex_path)
			# 5. Build meshes/materials
			m.start()

		return {"FINISHED"}


class IMPORT_MT_ymp(bpy.types.Menu):
	bl_label = "Yuke's Model Properties"

	def draw(self, context):
		layout = self.layout
		layout.operator(
			"import_scene.ymp_model_ps2", text="PlayStation 2 (.YMP, .YOBJ)"
		)
		layout.operator("import_scene.ymp_model_xbox", text="XBOX (.YMXEN, .JBOY)")


def menu_func_import(self, context):
	self.layout.menu("IMPORT_MT_ymp", text="Yuke's Models")


def register():
	bpy.utils.register_class(IMPORT_YMP_PS2)
	bpy.utils.register_class(IMPORT_YMP_XBOX)
	bpy.utils.register_class(IMPORT_MT_ymp)

	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

	bpy.utils.unregister_class(IMPORT_YMP_PS2)
	bpy.utils.unregister_class(IMPORT_YMP_XBOX)
	bpy.utils.unregister_class(IMPORT_MT_ymp)