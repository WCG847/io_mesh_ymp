bl_info = {
	"name": "YMP I/O",
	"author": "WCG847",
	"version": (4, 0, 0),
	"blender": (5, 0, 0),
	"location": "File/Import & File/Export",
	"description": "Import export YMP",
	"warning": "",
	"doc_url": "",
	"tracker_url": "",
	"category": "Import-Export",
}

from struct import unpack_from
import bpy
from bpy.types import AddonPreferences, Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import FloatProperty, StringProperty
from bpy.props import CollectionProperty
from bpy.types import OperatorFileListElement
import os

from .src.ps2.Import.skinmodel import SkinModel
from .src.XBOX.Import.skinmodel_ymxen import YMXEN_SkinModel, install_ymxen_springs, load_dds_from_memory
from .src.globals.camera import Camera
from .src.globals.light import Light
from .src.XBOX.Export.ymxen import YMXEN

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


class YMP_PreviewProps(bpy.types.PropertyGroup):
	preview_image: bpy.props.PointerProperty(
		name="SuperStar Preview",
		type=bpy.types.Image
	)


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
		tex_dir = self.directory

		# ---- Pre-scan directory once ----

		tex_filepacks = []
		bane_files = []
		abd_files = []
		for name in os.listdir(tex_dir):
			lname = name.lower()
			path = os.path.join(tex_dir, name)

			if lname.endswith(".tex"):
				with open(path, "rb") as tf:
					tex_filepacks.append(memoryview(tf.read()))

			elif lname.startswith("bane_muscle"):
				bane_files.append(path)

			elif lname.endswith(".abd"):
				abd_files.append(path)
			elif lname.startswith('superstarface'):
				img = bpy.data.images.load(path, check_existing=True)
				context.scene.preview_props.preview_image = img
			elif lname == 'camera.txt':
				Camera(path)

		tex_filepacks = tuple(tex_filepacks)
		# in IMPORT_YMP_XBOX.execute, after tex_filepacks = tuple(tex_filepacks)
		shared_textures = {}

		def build_shared_texture_cache(tex_filepacks):
			for filepack in tex_filepacks:
				header = filepack.cast("I")
				count = header[0]
				body = filepack[16:]
				for i in range(count):
					entry = body[i * 32 : (i + 1) * 32]
					name = entry[:16].tobytes().split(b"\x00")[0].decode("shift_jis", errors="replace")
					ext  = entry[16:20].tobytes().split(b"\x00")[0].decode("shift_jis", errors="replace")
					if ext != "dds":
						continue
					size, offset = unpack_from("<2I", entry, 20)
					data = filepack[offset : offset + size]
					key = name.lower()
					if key not in shared_textures:
						shared_textures[key] = load_dds_from_memory(name, data, prefix="shared")
		build_shared_texture_cache(tex_filepacks)


		# ---- Per-file processing ----

		for file_elem in self.files:
			full_path = bpy.path.abspath(self.directory + file_elem.name)

			with open(full_path, "rb") as f:
				if f.read(4) != b"JBOY":
					self.report({"WARNING"}, f"Skipping {file_elem.name}")
					continue

				size = int.from_bytes(f.read(4), "big")
				file = memoryview(bytearray(f.read(size)))

			m = YMXEN_SkinModel(file, self.scale)
			m.build_texture_slots()
			m.loaded_textures = shared_textures       # reuse!
			m.resolve_texture_slots()


			for path in bane_files:
				m.apply_muscle_config(path)

			for path in abd_files:
				m.create_attachment_points(path)

			m.start()

		bpy.ops.object.mode_set(mode="OBJECT")
		install_ymxen_springs()
		return {"FINISHED"}


class EXPORT_YMP_XBOX(Operator, ExportHelper):
	bl_idname = "export_scene.ymp_model_xbox"
	bl_label = "export YMP"
	filename_ext = ".ymxen"
	def execute(self, context):
		col = list(bpy.data.collections)
		arm = None
		for obj in bpy.context.scene.collection.objects:
			if obj.type == 'ARMATURE':
				arm = obj
				break
		assert arm
		textures = list(bpy.data.images)
		handler = YMXEN(col, arm, textures)
		handler.write()
		with open(self.filepath, 'wb') as ymp:
			for f in handler.structs:
				ymp.write(f.getvalue())
		return {'FINISHED'}

class IMPORT_MT_ymp(bpy.types.Menu):
	bl_label = "Yuke's Model Properties"

	def draw(self, context):
		layout = self.layout
		layout.operator(
			"import_scene.ymp_model_ps2", text="PlayStation 2 (.YMP, .YOBJ)"
		)
		layout.operator("import_scene.ymp_model_xbox", text="XBOX (.YMXEN, .JBOY)")


class EXPORT_MT_ymp(bpy.types.Menu):
	bl_label = "Yuke's Model Properties"

	def draw(self, context):
		layout = self.layout
		layout.operator("export_scene.ymp_model_xbox", text="XBOX")



class VIEW3D_PT_preview_panel(bpy.types.Panel):
	bl_label = "SuperStar Images"
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = "Preview"

	def draw(self, context):
		layout = self.layout
		props = context.scene.preview_props

		layout.template_ID_preview(
			props,
			"preview_image",
			new="image.new",
			open="image.open"
		)

def menu_func_import(self, context):
	self.layout.menu("IMPORT_MT_ymp", text="Yuke's Models")


def menu_func_export(self, context):
	self.layout.menu("EXPORT_MT_ymp", text="Yuke's Models")

def register():
	bpy.utils.register_class(YMP_PreviewProps)
	bpy.utils.register_class(VIEW3D_PT_preview_panel)

	bpy.types.Scene.preview_props = bpy.props.PointerProperty(
		type=YMP_PreviewProps
	)

	bpy.utils.register_class(IMPORT_YMP_PS2)
	bpy.utils.register_class(IMPORT_YMP_XBOX)
	bpy.utils.register_class(EXPORT_YMP_XBOX)
	bpy.utils.register_class(IMPORT_MT_ymp)
	bpy.utils.register_class(EXPORT_MT_ymp)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.append(menu_func_export)



def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
	bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

	del bpy.types.Scene.preview_props

	bpy.utils.unregister_class(VIEW3D_PT_preview_panel)
	bpy.utils.unregister_class(YMP_PreviewProps)

	bpy.utils.unregister_class(IMPORT_YMP_PS2)
	bpy.utils.unregister_class(IMPORT_YMP_XBOX)
	bpy.utils.unregister_class(EXPORT_YMP_XBOX)
	bpy.utils.unregister_class(IMPORT_MT_ymp)
	bpy.utils.unregister_class(EXPORT_MT_ymp)
