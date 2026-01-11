from enum import IntEnum, IntFlag
from typing import Iterable

class ENUM_TYPE(IntEnum):
	BYTE = 1
	WORD = 2
	DWORD = 3
def write_chunk(indices: Iterable[int]):
	if not indices:
		return
	allocated = memoryview(bytearray(b'\x00' * 8))
	TYPE = allocated.cast('I')
	TAG = int.from_bytes(b'POF0', 'big')
	TYPE[0] = TAG
	payload = memoryview(bytearray(b'\x00' * (len(indices) * 8)))
	base = 0
	for cp, offset in enumerate(indices):
		result = offset - base
		if result < 256:
			index = (ENUM_TYPE.BYTE << 6) | (result & 0x3F)
			put = 1
		elif result >= 256 and result < 65536:
			index = (ENUM_TYPE.WORD << 14) | (result & 0x3FFF)
			put = 2
		elif result >= 65536 and result < 4294967296:
			index = (ENUM_TYPE.DWORD << 30) | (result & 0x3FFFFFFF)
			put = 3
		match put:
			case 1:
				payload[cp] = index
			case 2:
				payload[cp*2:(cp*2)+2] = index.to_bytes(2, 'little')
			case 3:
				payload[cp*4:(cp*4)+4] = index.to_bytes(4, 'little')
		base = offset
		TYPE[1] = payload.tobytes().rstrip(b'\x00').__len__()
	return memoryview(allocated.tobytes() + payload.tobytes()) 