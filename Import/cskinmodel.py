import bpy
from struct import unpack, unpack_from
from io import BytesIO
from Import.subobject import CSubObject
from cskinmodel import CSkinModel

class CSkinModel:
	def Release(self):
		if self.Ymps is None:
			return
		else:
			self.Ymps.close()

	def Open(self, tagYmps):
		with open(tagYmps, 'rb', buffering=2048) as ymp:
			if (header := unpack('4s', ymp.read(4))[0].decode('ascii')) != 'YOBJ':
				raise ValueError(f'illegal header: {header}')
			chunkSize = unpack('<I', ymp.read(4))[0]
			self.Ymps = BytesIO(ymp.read(chunkSize))

	def Create(self):
		eof = unpack_from('<I', self.Ymps.getbuffer(), 4)
		self.Ymps.seek(16)
		objectcount, bonecount, texturecount, \
			objectpointer, bonepointer, texturepointer, \
			vgpointer, vgcount \
			= unpack('<8I', self.Ymps.read(4 * 8))
		self.Ymps.seek(objectpointer)
		subobjectcls = CSubObject()
		subobjectcls.Create(objectcount, self.Ymps)

