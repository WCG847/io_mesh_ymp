import math
import bpy
from dataclasses import dataclass
from mathutils import Matrix, Vector


def engine_to_blender(v: Vector) -> Vector:
    return Vector((v.x, v.z, -v.y))


class Camera:
    @dataclass(slots=True)
    class INFO:
        area: Vector
        radius: float
        position: Vector

    def __init__(self, path: str):
        self.read(path)

    def read(self, path: str):
        details: list[Camera.INFO] = []
        with open(path, "r", encoding="shift_jis") as param:
            while line := param.readline():
                line = line.split(";", 1)[0].strip()
                if not line:
                    continue
                if line.startswith("//"):
                    break

                l = line.split()

                area = Vector([float(x) for x in l[:3]])
                radius = float(l[3])
                positions = Vector([float(x) for x in l[4:7]])
                details.append(Camera.INFO(area, radius, positions))
        self.objs: list[bpy.types.Object] = []
        for i in range(len(details)):
            datablock = bpy.data.cameras.new(f"yCamera{i}")
            o = bpy.data.objects.new("YCAMERA", datablock)
            bpy.context.scene.collection.objects.link(o)
            self.objs.append(o)
        for detail, obj in zip(details, self.objs):
            e = bpy.data.objects.new("SPHERE", None)
            bpy.context.scene.collection.objects.link(e)
            e.location = engine_to_blender(detail.area)

            e.empty_display_type = "SPHERE"
            e.empty_display_size = detail.radius
            obj.location = engine_to_blender(detail.position)