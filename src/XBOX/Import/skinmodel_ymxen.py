import math
from typing import TextIO
from bpy.types import ParticleSettingsTextureSlot
from mathutils import Euler, Matrix, Vector, Quaternion
from ...globals.be import get_view, resolve_view
from struct import unpack_from, unpack
import bpy
import tempfile
import uuid

_HANDLER_KEY = "_ymxen_spring_handler_installed"


def _clamp(v, lo, hi):
	return max(lo, min(hi, v))


def _clamp_euler_xyz(e: Euler, lx: float, ly: float, lz: float) -> Euler:
	# lx/ly/lz are treated as max absolute angles (radians) around local axes
	# If your config is degrees, convert when reading: radians = deg * pi/180
	x = _clamp(e.x, -lx, lx) if lx > 0.0 else e.x
	y = _clamp(e.y, -ly, ly) if ly > 0.0 else e.y
	z = _clamp(e.z, -lz, lz) if lz > 0.0 else e.z
	return Euler((x, y, z), "XYZ")


def _spring_step_pose_bone(pb: bpy.types.PoseBone, dt: float):
	# Only process bones that have params
	if "ymxen_spring_k" not in pb:
		return

	k = float(pb["ymxen_spring_k"])
	damp = float(pb["ymxen_damping"])
	visc = float(pb["ymxen_viscosity"])
	grav = float(pb["ymxen_gravity"])
	tscale = float(pb["ymxen_time"])

	lx = float(pb.get("ymxen_lx", 0.0))
	ly = float(pb.get("ymxen_ly", 0.0))
	lz = float(pb.get("ymxen_lz", 0.0))

	# Protect against nonsense
	dt = max(dt, 1e-6)
	if tscale > 1e-6:
		dt = dt / tscale  # bigger time => slower response (common convention)

	# Current basis rotation (extra rotation on top of rest)
	q = pb.rotation_quaternion.copy()

	# Angular velocity state (local axes of the bone basis)
	omega = Vector(pb["ymxen_omega"])

	# --- Spring force: pull back to rest (identity quaternion) ---
	# Error quaternion from current -> rest
	q_err = Quaternion((1.0, 0.0, 0.0, 0.0)) @ q.inverted()
	axis, angle = q_err.to_axis_angle()

	# Normalise angle to [-pi, pi] for sane behaviour
	if angle > math.pi:
		angle -= 2.0 * math.pi

	# Torque-like term (axis * angle). This is the “spring”
	spring = Vector(axis) * (angle * k)

	# --- Damping: resist angular velocity ---
	damping_term = -omega * max(0.0, damp)

	# --- Viscosity: extra “drag” each step (simple exponential-ish decay) ---
	# Treat viscosity as a per-step multiplier towards 0
	visc_factor = 1.0 / (1.0 + max(0.0, visc) * dt)

	# --- Gravity: bias towards “down” in armature space, converted to bone local ---
	# This is a crude but useful approach: try to align bone's local +Y with world -Z.
	# If your bone's "forward" axis isn't Y, change the local vector below.
	arm_obj = pb.id_data  # Armature object
	down_arm = (
		arm_obj.matrix_world.inverted().to_3x3() @ Vector((0, 0, -1))
	).normalized()
	local_forward = Vector((0, 1, 0))  # bone forward axis assumption
	# Torque direction is cross product: rotate forward towards down
	grav_torque = local_forward.cross(down_arm) * grav

	# Accumulate “angular acceleration”
	alpha = spring + damping_term + grav_torque

	# Integrate angular velocity
	omega = (omega + alpha * dt) * visc_factor

	# Apply small-angle rotation update
	# dq ~ rotation from omega*dt about local axes
	ax = omega.x * dt
	ay = omega.y * dt
	az = omega.z * dt
	dq = (
		Quaternion((1, 0, 0), ax)
		@ Quaternion((0, 1, 0), ay)
		@ Quaternion((0, 0, 1), az)
	)

	q_new = (dq @ q).normalized()

	# Clamp in XYZ euler (simple and imperfect, but works for many rigs)
	e = q_new.to_euler("XYZ")
	e = _clamp_euler_xyz(e, lx, ly, lz)
	q_new = e.to_quaternion()

	# Write back
	pb.rotation_quaternion = q_new
	pb["ymxen_omega"] = [omega.x, omega.y, omega.z]


def _ymxen_spring_handler(scene):
	fps = scene.render.fps / max(1, scene.render.fps_base)
	dt = 1.0 / max(1e-6, fps)

	for obj in scene.objects:
		if obj.type != "ARMATURE":
			continue
		for pb in obj.pose.bones:
			_spring_step_pose_bone(pb, dt)


def install_ymxen_springs():
	if _ymxen_spring_handler in bpy.app.handlers.frame_change_pre:
		return
	bpy.app.handlers.frame_change_pre.append(_ymxen_spring_handler)


def uninstall_ymxen_springs():
	if _ymxen_spring_handler in bpy.app.handlers.frame_change_pre:
		bpy.app.handlers.frame_change_pre.remove(_ymxen_spring_handler)
	setattr(bpy.app.handlers, _HANDLER_KEY, False)


def load_dds_from_memory(name: str, data: bytes, prefix: str):
	tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dds")
	tmp.write(data)
	tmp.close()

	img = bpy.data.images.load(tmp.name, check_existing=True)
	img.name = f"{prefix}_{name}"
	img.alpha_mode = "CHANNEL_PACKED"
	return img


def link(obj: bpy.types.Object, mode="EDIT"):
	bpy.context.collection.objects.link(obj)
	bpy.context.view_layer.objects.active = obj
	obj.select_set(True)

	bpy.ops.object.mode_set(mode="OBJECT")
	if mode != "OBJECT":
		bpy.ops.object.mode_set(mode=mode)


class YMXEN_SkinModel:
	AXIS_FIX = Matrix.Rotation(math.radians(-90.0), 4, "X")

	def __init__(self, file: memoryview, scale: float):
		self.uid = uuid.uuid4().hex[:8]

		if not file:
			return
		self.file = file
		self.scale = scale
		self.use_tangents = (
			True if unpack(">I", file[:4])[0] == 16 else False
		)  # also a hint that Autodesk is used (i.e Biped rigs)
		if self.use_tangents:
			self.scale += 10.0
		self.create()

	def create_attachment_points(self, path: str):
		try:
			with open(path, "rb") as abd:
				eof = [abd.seek(0, 2), abd.tell(), abd.seek(0)][1]
				while abd.tell() != eof:
					id1, bone_id, x, y, z = unpack("<2h3f", abd.read(16))
					offset_vectors = YMXEN_SkinModel.AXIS_FIX @ Vector((x, y, z))
					if id1 == -1:
						continue
					else:
						id1 -= 1
					if bone_id == -1:
						continue
					else:
						bone_id -= 1
					empty = bpy.data.objects.new(f"abd{id1}", None)
					empty.parent = self.armature
					empty.parent_type = "BONE"
					empty.parent_bone = self.bone_names[bone_id]
					empty.matrix_parent_inverse.identity()
					empty.location = offset_vectors
					bpy.context.scene.collection.objects.link(empty)
					empty.hide_viewport = True
					empty.hide_select = True
		except Exception:
			return

	def get_texture(self, index: int):
		if index is None:
			return None
		if 0 <= index < len(self.texture_slots):
			return self.texture_slots[index]
		return None

	def create(self):
		bone_count: int = unpack_from(">I", self.file, 24)[0]
		bone = get_view(self.file, 32)
		s = bpy.data.armatures.new("0")
		self.armature = bpy.data.objects.new("ymxenBone", s)
		NULL = -1
		link(self.armature)
		self.bones: list[bpy.types.EditBone] = [None] * bone_count
		self.world = [Matrix.Identity(4) for i in range(bone_count)]
		self.local = [Matrix.Identity(4) for i in range(bone_count)]
		self.bone_names = [None] * bone_count
		for i in range(bone_count):
			b = bone[i * 80 : (i * 80) + 80]
			raw = b.cast("c")[:16].tobytes().split(b"\x00", 1)[0]

			safe_name = raw.decode("shift_jis", errors="replace")
			print("YMXEN_SkinModel: Added bone %s" % safe_name)

			bpy_bone = self.armature.data.edit_bones.new(safe_name)

			self.bones[i] = bpy_bone
			self.bone_names[i] = safe_name

			positions = Vector(unpack_from(">3f", b, 16))
			rotations = Euler(unpack_from(">3f", b, 32), "ZYX")
			parent = unpack_from(">i", b, 48)[0]
			local = Matrix.LocRotScale(positions, rotations, None)

			if parent == NULL:
				if not self.use_tangents:
					self.world[i] = YMXEN_SkinModel.AXIS_FIX @ local
				else:
					self.world[i] = local
			else:
				self.world[i] = self.world[parent] @ local

				bpy_bone.parent = self.bones[parent]

		DEFAULT_LEN = 0.05 * self.scale
		parents = [
			unpack(">i", bone[i * 80 : (i * 80) + 80][48:52])[0]
			for i in range(bone_count)
		]
		for i, bpy_bone in enumerate(self.bones):
			mat = self.world[i]

			head = mat.to_translation()
			children = [j for j, p in enumerate(parents) if p == i]
			if not children:
				bpy_bone.use_deform = False
				bpy_bone.hide = True
			if children:
				child_head = self.world[children[0]].to_translation()
				vec = child_head - head
				direction = vec.normalized()
				length = vec.length
			else:
				rot = mat.to_quaternion()
				direction = rot @ Vector((0, 1, 0))
				length = DEFAULT_LEN

			bpy_bone.head = head
			bpy_bone.tail = head + direction * max(length, 1e-5)
			bpy_bone.align_roll(mat.to_3x3() @ Vector((0, 0, 1)))

		self.texture_slots: list[bpy.types.Image | None] = []

	def set_textures(self, filepack: tuple[memoryview, ...]):
		header = filepack.cast("I")
		count = header[0]
		body = filepack[16:]

		local_slots = [None] * count

		for i in range(count):
			START = i * 32
			got = body[START : START + 32]

			name = (
				got[:16]
				.tobytes()
				.split(b"\x00")[0]
				.decode("shift_jis", errors="replace")
			)
			ext = (
				got[16:20]
				.tobytes()
				.split(b"\x00")[0]
				.decode("shift_jis", errors="replace")
			)
			print("YMXEN_SkinModel: Added texture %s" % name)
			size, offset = unpack_from("<2I", got, 20)

			if ext != "dds":
				continue

			data = filepack[offset : offset + size]
			img = load_dds_from_memory(name, data)

			local_slots[i] = img

		self.texture_slots = local_slots

	def start(self):
		object_groups = get_view(self.file, 40)
		assert object_groups != -1
		obj_g_count = unpack_from(">I", self.file, 44)[0]
		self.cols: list[bpy.types.Collection] = []
		for i in range(obj_g_count):
			o = object_groups[i * 32 : (i * 32) + 32].cast("c")
			name = (
				o[:16]
				.tobytes()
				.split(b"\x00", 1)[0]
				.decode("shift_jis", errors="replace")
			)
			print("YMXEN_SkinModel: Added collection %s" % name)
			collect = bpy.data.collections.new(name)
			bpy.context.scene.collection.children.link(collect)
			self.cols.append(collect)
		SIZEOF = 184 if self.use_tangents else 180
		subobject_count = unpack_from(">I", self.file, 16)[0]
		subobject_ptr = get_view(self.file, 20)
		for i in range(subobject_count):
			_ = bpy.data.meshes.new("ymxenSubObject")

			bpy_obj = bpy.data.objects.new(f"Object{i:02d}", _)
			subobj = subobject_ptr[i * SIZEOF : (i * SIZEOF) + SIZEOF]
			vertex_count, unk_bool, bone_count = unpack(">3I", subobj[:12])
			unk_bool = bool(unk_bool)  # treated as 32-bit, akin to Windows' BOOL
			bone_indices = unpack(">20i", subobj[12:92])  # dont ask
			(
				bone_weight_count,
				og_index,
				unk_bool_2,
				vert_offset,
				weight_offset,
				uv_offset,
			) = unpack(">6I", subobj[92:116])
			# Custom tangents is a bit tricky in Blender, we just calculate it automatically
			if self.use_tangents:
				# earlier revisions neglected this field in serialisation
				tangent_offset = unpack(">I", subobj[116:120])[0]
			else:
				tangent_offset = None  # just use Blender's default tangents
			fmt = ">I16s7If3f"
			offset = 120 if self.use_tangents else 116

			(
				effect_technique_index,
				shader_name,
				unk_int_1,
				unk_int_2,
				material_count,
				material_offset,
				batch_offset,
				redundant_vertex_count,
				unk_int_3,
				radius,
				cx,
				cy,
				cz,
			) = unpack_from(fmt, subobj, offset)

			centre = (cx, cy, cz)

			material = resolve_view(self.file, material_offset)
			batch = resolve_view(self.file, batch_offset)
			vertices = resolve_view(self.file, vert_offset)
			weights = resolve_view(self.file, weight_offset)
			uvs = resolve_view(self.file, uv_offset)
			if tangent_offset:
				tangent = resolve_view(self.file, tangent_offset)
			else:
				tangent = None
			self.cols[og_index].objects.link(bpy_obj)
			centre = YMXEN_SkinModel.AXIS_FIX @ Vector(centre)
			sphere = bpy.data.objects.new(f"ySphere_{i:02d}", None)
			sphere.empty_display_type = "SPHERE"
			sphere.empty_display_size = radius
			sphere.location = centre
			self.cols[og_index].objects.link(sphere)

			sphere.parent = bpy_obj
			sphere.hide_select = True
			sphere.hide_render = True
			sphere.hide_viewport = True

			bpy_obj.display_type = "TEXTURED"
			bpy_obj.parent = self.armature
			mod = bpy_obj.modifiers.new(name="Armature", type="ARMATURE")
			mod.object = self.armature

			for b in bone_indices:
				if b != -1:
					idx = b - 1
					if not idx:
						continue
					name = self.bone_names[idx]

					if name not in bpy_obj.vertex_groups:
						bpy_obj.vertex_groups.new(name=name)
			NORMALS, XYZS, DIFFUSES = self.send_fvf(vertex_count, vertices, bpy_obj)
			NORMALS = [-n for n in NORMALS]
			vertex_weights = self.send_weights(vertex_count, weights, bone_count)

			for v_idx, influences in enumerate(vertex_weights):
				if not influences:
					continue

				total = sum(w for _, w in influences)
				if total <= 0.0:
					continue

				for bone_idx, w in influences:
					bone_name = self.bone_names[bone_idx]

					group = bpy_obj.vertex_groups.get(bone_name)
					if group:
						group.add([v_idx], w / total, "REPLACE")
			faces = self.send_faces(batch, bpy_obj)
			bpy_obj.data.from_pydata(XYZS, [], faces)
			bpy_obj.data.normals_split_custom_set_from_vertices(NORMALS)
			UVS = self.send_TEXCOORD(uvs, vertex_count)

			mesh = bpy_obj.data
			uv_layer = mesh.uv_layers.new(name="TEXCOORD0").data

			for poly in mesh.polygons:
				for loop_idx in poly.loop_indices:
					vert_idx = mesh.loops[loop_idx].vertex_index
					uv_layer[loop_idx].uv = UVS[vert_idx]

			col = bpy_obj.data.color_attributes.new(
				name="D3DFVF_DIFFUSE", domain="POINT", type="BYTE_COLOR"
			)

			for i, d in enumerate(DIFFUSES):
				a = (d >> 24) & 0xFF
				r = (d >> 16) & 0xFF
				g = (d >> 8) & 0xFF
				b = d & 0xFF
				col.data[i].color = (r, g, b, a)
			if uv_layer:
				mesh.calc_tangents(uvmap="TEXCOORD0")
			self.set_shader(
				shader_name.split(b"\x00")[0].decode("shift_jis", errors="replace"),
				effect_technique_index,
				material,
				material_count,
				bpy_obj,
			)

	def set_shader(
		self,
		name: str,
		effect_technique_index: int,
		material: memoryview,
		material_count: int,
		subobj: bpy.types.Object,
	):
		noise_node = None
		mask_node = None
		fresnel_node = None
		noise_tex = None
		noise_mask = None

		def ensure_noise():
			nonlocal noise_node
			if noise_node is None:
				noise_node = nodes.new("ShaderNodeTexNoise")
				noise_node.inputs["Scale"].default_value = 12.0
				noise_node.inputs["Detail"].default_value = 2.0
			return noise_node

		mat = bpy.data.materials.new(name=f"{self.uid}_{name}")
		print(f"created material: {mat.name}")
		nodes = mat.node_tree.nodes
		links = mat.node_tree.links
		nodes.clear()

		out = nodes.new("ShaderNodeOutputMaterial")
		bsdf = nodes.new("ShaderNodeBsdfPrincipled")
		links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

		base_col = nodes.new("ShaderNodeRGB")
		base_col.outputs["Color"].default_value = (1, 1, 1, 1)
		diffuse_source = base_col.outputs["Color"]
		ao_level = 1.0
		ao_with_diffuse = 1.0
		# create once per material
		texcoord = nodes.new("ShaderNodeTexCoord")
		mapping = nodes.new("ShaderNodeMapping")
		links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

		# helper to attach mapping to any image texture node
		def hook_mapping(img_tex_node):
			links.new(mapping.outputs["Vector"], img_tex_node.inputs["Vector"])

		spec_base = 0
		power_base = 0
		level_base = 0

		print("YMXEN_SkinModel: Added shader %s" % name)
		for i in range(material_count):
			START = i * 4
			END = (i * 4) + 4
			got = material[START:END]
			offset = unpack(">I", got)[0]
			material_view = resolve_view(self.file, offset)
			MAT_name = (
				unpack_from("16s", material_view, 0)[0]
				.split(b"\x00")[0]
				.decode("shift_jis", errors="replace")
			)
			mat_type, mat_size = unpack_from(">2H", material_view, 16)
			match mat_type:
				case 13:
					data = unpack_from(">4f", material_view, 20)
				case 10:
					data = unpack_from(">1f", material_view, 20)
				case 16:
					data = unpack_from(">i", material_view, 20)  # microsoft style BOOL

				case 5:
					data = list(unpack_from(">i", material_view, 20))
					if data[0] == -1:
						data[0] = None
					data = tuple(data)

				case 15:
					data = unpack_from(">I", material_view, 20)
			print("YMXEN_SkinModel: Added material %s" % MAT_name)
			match MAT_name:
				case "g_f4LightVec3":
					pass
				case "g_f4Diffuse3":
					pass
				case "g_bDifLightSpc3":
					pass
				case "g_f4MatAmbCol":
					pass
				case "g_f4MatDifCol":
					r, g, b, a = data
					base_col.outputs["Color"].default_value = (r, g, b, a)

				case "g_f4SpecularCol":
					r, g, b, a = data
					bsdf.inputs["Specular Tint"].default_value = (r, g, b, a)

				case 'g_fSpecLev':
					(v,) = unpack_from(">f", material_view, 20)
					bsdf.inputs["Specular IOR Level"].default_value = v / 10

				case "g_fSpecularLev":
					(v,) = unpack_from(">f", material_view, 20)
					bsdf.inputs["Specular IOR Level"].default_value = v

				case "g_fSpecPow":
					(p,) = unpack_from(">f", material_view, 20)
					bsdf.inputs["Roughness"].default_value = p / 10


				case "g_iSpecularPow":
					(p,) = unpack_from(">i", material_view, 20)
					bsdf.inputs["Roughness"].default_value = max(
						0.0, min(1.0, 1.0 - (p / 128.0))
					)

				case "g_fHDRAlpha":
					(ha,) = unpack_from(">f", material_view, 20)
					bsdf.inputs["Emission Strength"].default_value = 1.0 - ha
				case "g_bUseRefRegMap":
					mat["g_bUseRefRegMap"] = bool(data[0])

				case "g_bReflectAdd":
					mat["g_bReflectAdd"] = bool(data[0])
				case "g_fReflectAlpha":
					mat["g_fReflectAlpha"] = float(data[0])
				case "g_fSweatLev":
					(sweat,) = unpack_from(">f", material_view, 20)
					sweat = max(0.0, sweat)
					bsdf.inputs["Coat Weight"].default_value = _clamp(sweat, 0.0, 1.0)
					bsdf.inputs["Coat Roughness"].default_value = 0.1

				case "texDiffuse" | "g_mDiffusePrm":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img

						tex.interpolation = "Cubic"
						diffuse_source = tex.outputs["Color"]
					else:
						diffuse_source = base_col.outputs["Color"]

				case "g_mCubeLPrm":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						env = nodes.new("ShaderNodeTexEnvironment")
						env.image = img

						fresnel_node = nodes.new("ShaderNodeFresnel")
						fresnel_node.inputs["IOR"].default_value = 1.45

						mix = nodes.new("ShaderNodeMixRGB")
						mix.blend_type = "MIX"

						links.new(fresnel_node.outputs["Fac"], mix.inputs["Fac"])
						links.new(env.outputs["Color"], mix.inputs[2])
						links.new(diffuse_source, mix.inputs[1])

						diffuse_source = mix.outputs["Color"]



				case "g_mNoiseTilePrm":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						noise_tex = nodes.new("ShaderNodeTexImage")
						noise_tex.image = img
						noise_tex.image.colorspace_settings.name = "Non-Color"
						noise_tex.interpolation = "Linear"


				case "g_mMaskPrm":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						mask_node = nodes.new("ShaderNodeTexImage")
						mask_node.image = img
						mask_node.image.colorspace_settings.name = "Non-Color"

				case 'g_fSSLevel':
					level = data[0]
					bsdf.inputs["Subsurface Weight"].default_value = level
				case 'g_fSSStart':
					pass
				case 'g_fSSEnd':
					pass
				case 'g_f4SSColor':
					pass

				case 'g_fSpecLevBase':
					pass
				case 'g_fSpecPwBase':
					pass
				case "g_f4Ref_COL":
					r, g, b, a = data
					bsdf.inputs["Specular Tint"].default_value = (r, g, b, 1.0)

				case "g_f4Ref_DOT":
					pass  # handled implicitly via Fresnel

				case "g_f4NoiseTDiff":
					if noise_tex:
						mul = nodes.new("ShaderNodeMixRGB")
						mul.blend_type = "MULTIPLY"
						mul.inputs["Fac"].default_value = data[3] if len(data) == 4 else 0.3

						links.new(diffuse_source, mul.inputs[1])
						links.new(noise_tex.outputs["Color"], mul.inputs[2])

						if noise_mask:
							links.new(noise_mask.outputs["Color"], mul.inputs["Fac"])

						diffuse_source = mul.outputs["Color"]

				case "g_f4NoiseTSpec":
					if noise_tex:
						ramp = nodes.new("ShaderNodeValToRGB")

						links.new(noise_tex.outputs["Color"], ramp.inputs["Fac"])
						links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])


				case "g_f4NoiseTBump":
					if noise_tex:
						bump = nodes.new("ShaderNodeBump")
						bump.inputs["Strength"].default_value = data[3] if len(data) == 4 else 0.2

						links.new(noise_tex.outputs["Color"], bump.inputs["Height"])
						links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

				case "g_f4NoiseTCnt":
					if noise_tex:
						scale = sum(data[:3]) / 3.0
						noise_tex.extension = "REPEAT"



				case "texSpecularMap":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img
						tex.image.colorspace_settings.name = "Non-Color"

						inv = nodes.new("ShaderNodeInvert")
						links.new(tex.outputs["Color"], inv.inputs["Color"])
						links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])

				case "texNormal" | "g_mNormalFxPrm":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if img:
						tex = nodes.new("ShaderNodeTexImage")
						tex.image = img
						tex.image.colorspace_settings.name = "Non-Color"
						nrm = nodes.new("ShaderNodeNormalMap")
						links.new(tex.outputs["Color"], nrm.inputs["Color"])
						links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])

				case "texSphRefction":
					pass
				case "texRefctionReg":
					pass
				case "g_fAmbOccLev":
					(ao_level,) = data
				case "g_fAmbOccDif":
					(ao_with_diffuse,) = data

				# case "g_fScrollU":
				# 	(uv_scroll[1]["u"],) = data
				# case "g_fScrollV":
				# 	(uv_scroll[1]["v"],) = data

				# case "g_fScrollU2":
				# 	(uv_scroll[2]["u"],) = data
				# case "g_fScrollV2":
				# 	(uv_scroll[2]["v"],) = data

				# case "g_fScrollU3":
				# 	(uv_scroll[3]["u"],) = data
				# case "g_fScrollV3":
				# 	(uv_scroll[3]["v"],) = data

				# case "g_fScrollU4":
				# 	(uv_scroll[4]["u"],) = data
				# case "g_fScrollV4":
				# 	(uv_scroll[4]["v"],) = data

				# case "g_fSL_Scale":
				# 	(sl_scale,) = data

				# case "texUVScroll2":
				# 	tex_idx = data[0]
				# 	img = self.get_texture(tex_idx)
				# 	if img:
				# 		tex = nodes.new("ShaderNodeTexImage")
				# 		tex.image = img
				# 		tex_uv_scrolls[1] = tex

				# 		tex.interpolation = "Cubic"
				# case "texUVScroll3":
				# 	tex_idx = data[0]
				# 	img = self.get_texture(tex_idx)
				# 	if img:
				# 		tex = nodes.new("ShaderNodeTexImage")
				# 		tex.image = img
				# 		tex_uv_scrolls[2] = tex

				# 		tex.interpolation = "Cubic"
				# case "texUVScroll4":
				# 	tex_idx = data[0]
				# 	img = self.get_texture(tex_idx)
				# 	if img:
				# 		tex = nodes.new("ShaderNodeTexImage")
				# 		tex.image = img
				# 		tex_uv_scrolls[3] = tex

				# 		tex.interpolation = "Cubic"

				case "texOcclusion":
					tex_idx = data[0]
					img = self.get_texture(tex_idx)
					if not img:
						continue

					ao_strength = max(0.0, min(1.0, ao_level * ao_with_diffuse))

					# AO texture (linear data)
					ao_tex = nodes.new("ShaderNodeTexImage")
					ao_tex.image = img
					ao_tex.image.colorspace_settings.name = "Non-Color"

					# Convert AO RGB → scalar
					ao_bw = nodes.new("ShaderNodeRGBToBW")

					# Multiply scalar AO into diffuse
					mul = nodes.new("ShaderNodeMixRGB")
					mul.blend_type = "MULTIPLY"
					mul.inputs["Fac"].default_value = ao_strength

					links.new(ao_tex.outputs["Color"], ao_bw.inputs["Color"])
					links.new(diffuse_source, mul.inputs[1])
					links.new(ao_bw.outputs["Val"], mul.inputs[2])

					diffuse_source = mul.outputs["Color"]

				case _:
					pass
		links.new(diffuse_source, bsdf.inputs["Base Color"])
		subobj.data.materials.append(mat)

	def send_TEXCOORD(self, uv: memoryview, vertex: int):
		SIZEOF = 8
		UVS = []
		for i in range(vertex):
			view = uv[i * SIZEOF : (i * SIZEOF) + SIZEOF]
			U, V = unpack(">2f", view)
			V = 1.0 - V
			UVS.append((U, V))
		return UVS

	def send_faces(self, batch: memoryview, subobj: bpy.types.Object):
		MAGIC = 6
		view = batch
		FACES: list[tuple[int, ...]] = []
		while True:
			if unpack(">I", view[:4])[0] != MAGIC:
				break
			view = view[4:]
			face_count = unpack(">I", view[:4])[0]
			view = view[4:]
			face_offset = unpack(">I", view[:4])[0]
			view = view[4:]
			face_view = resolve_view(self.file, face_offset)
			cur_faces = []
			for i in range(face_count):
				cur_faces.append(unpack(">H", face_view[i * 2 : (i * 2) + 2])[0])
			FACES.append(tuple(cur_faces))
		faces = []

		for strip in FACES:
			if len(strip) < 3:
				continue

			for i in range(len(strip) - 2):
				a, b, c = strip[i], strip[i + 1], strip[i + 2]

				# Degenerate triangle, skip it
				if a == b or b == c or a == c:
					continue

				# Flip winding every other triangle
				if i & 1:
					tri = (a, c, b)
				else:
					tri = (a, b, c)

				# DX9 (LH, CW) → Blender (RH, CCW)
				faces.append((tri[0], tri[2], tri[1]))

		mesh = subobj.data
		return faces

	def send_weights(self, vertex_count: int, weights: memoryview, bones: int):
		MORE = 0xFF
		offset = 0
		vertex_weights: list[list[tuple[int, float]]] = []

		for v in range(vertex_count):
			influences: list[tuple[int, float]] = []

			bone_index, weight, status = unpack_from(">IfI", weights, offset)
			offset += 16

			if 0 <= bone_index < bones and weight > 0.0:
				influences.append((bone_index, weight))

			if (status & 0xFF) == MORE:
				while True:
					w = unpack_from(">f", weights, offset)[0]
					offset += 4

					idx = unpack_from(">I", weights, offset)[0]
					offset += 4

					if 0 <= idx < bones and w > 0.0:
						influences.append((idx, w))
					else:
						break

			vertex_weights.append(influences)

		return vertex_weights

	def build_texture_slots(self):
		textures = get_view(self.file, 0x24)
		count = unpack_from(">I", self.file, 0x1C)[0]

		self.texture_slots = []
		self.texture_names = []

		for i in range(count):
			entry = textures[i * 16 : (i + 1) * 16]
			name = (
				unpack("16s", entry)[0]
				.split(b"\x00", 1)[0]
				.decode("shift_jis", errors="replace")
			)
			self.texture_slots.append(None)
			self.texture_names.append(name.lower())

	def load_tex_files(self, filepacks: tuple[memoryview, ...]):
		self.loaded_textures: dict[str, bpy.types.Image] = {}

		for filepack in filepacks:
			header = filepack.cast("I")
			count = header[0]
			body = filepack[16:]

			for i in range(count):
				entry = body[i * 32 : (i + 1) * 32]

				name = (
					entry[:16]
					.tobytes()
					.split(b"\x00")[0]
					.decode("shift_jis", errors="replace")
				)
				ext = (
					entry[16:20]
					.tobytes()
					.split(b"\x00")[0]
					.decode("shift_jis", errors="replace")
				)
				if ext != "dds":
					continue

				size, offset = unpack_from("<2I", entry, 20)
				data = filepack[offset : offset + size]

				key = name.lower()
				if key not in self.loaded_textures:
					self.loaded_textures[key] = load_dds_from_memory(
						name, data, self.uid
					)

	def resolve_texture_slots(self):
		for i, name in enumerate(self.texture_names):
			img = self.loaded_textures.get(name)
			if img:
				self.texture_slots[i] = img

	def send_fvf(self, count: int, vertices: memoryview, subobj: bpy.types.Object):
		packet = unpack(">I", vertices[:4])[0]
		FVF_PACKET = resolve_view(self.file, packet)
		SIZEOF = 28
		NORMALS: list[Vector] = []
		XYZS: list[Vector] = []
		DIFFUSES: list[int] = []
		for i in range(count):
			packet = FVF_PACKET[i * SIZEOF : (i * SIZEOF) + SIZEOF]
			XYZ = YMXEN_SkinModel.AXIS_FIX @ Vector(unpack_from(">3f", packet, 0))
			NORMAL = YMXEN_SkinModel.AXIS_FIX @ Vector(unpack_from(">3f", packet, 12))
			DIFFUSE = unpack_from(">i", packet, 24)[0]
			NORMALS.append(NORMAL)
			XYZS.append(XYZ)
			DIFFUSES.append(DIFFUSE)
		return NORMALS, XYZS, DIFFUSES

		# Create colour attribute

	def match_bones(self, config_name: str):

		matches = []
		for bone in self.armature.pose.bones:
			if bone.name == config_name or bone.name.endswith(f"_{config_name}"):
				matches.append(bone)
		return matches

	def apply_muscle_spring(self, bone: bpy.types.PoseBone, values: tuple[float, ...]):
		viscosity, gravity, spring_k, damping, time, lx, ly, lz = values

		# Store params
		bone["ymxen_viscosity"] = float(viscosity)
		bone["ymxen_gravity"] = float(gravity)
		bone["ymxen_spring_k"] = float(spring_k)
		bone["ymxen_damping"] = float(damping)
		bone["ymxen_time"] = float(time)
		bone["ymxen_lx"] = float(lx)
		bone["ymxen_ly"] = float(ly)
		bone["ymxen_lz"] = float(lz)

		# State (angular velocity in local/basis space)
		bone["ymxen_omega"] = [0.0, 0.0, 0.0]

		# Make sure we have a stable rotation representation
		bone.rotation_mode = "QUATERNION"

		# Nuke the “pretend physics” constraints if they exist
		for c in list(bone.constraints):
			if c.type in {"COPY_ROTATION", "DAMPED_TRACK"}:
				bone.constraints.remove(c)

	def apply_muscle_config(self, cfg_path: str):
		bones_cfg = self.read_muscle_springs(cfg_path)

		bpy.context.view_layer.objects.active = self.armature
		bpy.ops.object.mode_set(mode="POSE")

		for cfg_name, values in bones_cfg:
			targets = self.match_bones(cfg_name)
			for pb in targets:
				self.apply_muscle_spring(pb, values)

		bpy.ops.object.mode_set(mode="OBJECT")

	def read_muscle_springs(self, file: str):
		bones: list[tuple[str, tuple[float, ...]]] = []

		with open(file, "r", encoding="shift_jis") as f:
			header = f.readline().strip()
			if header != ";バネ系筋肉の設定":
				return bones

			f.readline()  # skip comment line

			while True:
				line = f.readline()
				if not line:
					break

				line = line.strip()
				if not line or not line.startswith(";"):
					continue

				name = line[1:].strip()

				values_line = f.readline()
				if not values_line:
					break

				values = tuple(map(float, values_line.split()))
				bones.append((name, values))

		return bones
