import bpy

class Light:
	def __init__(self, path: str):
		datablock = bpy.data.lights.new('ymxenLight', 'SPOT')