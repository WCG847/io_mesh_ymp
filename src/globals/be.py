
from struct import unpack

def get_view(view: memoryview, offset: int):
	v = view.cast('B')
	pointer = unpack('>I', view[offset:offset+4])[0]
	return v[pointer:]