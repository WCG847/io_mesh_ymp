from enum import IntEnum, auto
from io import BytesIO
from typing import Iterable
from struct import pack

class YCHUNK_TYPE(IntEnum):
	BYTE = auto()
	WORD = auto()
	DWORD = auto()


def write_chunk(tag: bytes, payload: memoryview, pointers: Iterable[int], format: str = '>') -> memoryview:
	TAG = b'POF0'
	base = 0
	p = BytesIO()
	p.write(pack(f'{format}2I', int.from_bytes(tag[::-1]), len(payload)))
	p.write(payload)
	footer = BytesIO()
	for ptr in sorted(pointers):
		delta = ptr - base
		base = ptr
		match delta:
			case d if 0 <= d < 256:
				byte = (int(YCHUNK_TYPE.BYTE) << 6) | (d & 0x3F)
				fmt = f'{format}B'

			case d if 256 <= d < 65536:
				byte = (int(YCHUNK_TYPE.WORD) << 14) | (d & 0x3FFF)
				fmt = f'{format}H'

			case d if 65536 <= d < 4294967296:
				byte = (int(YCHUNK_TYPE.DWORD) << 30) | (d & 0x3FFFFFFF)
				fmt = f'{format}I'

			case _:
				raise ValueError(f"Invalid delta {delta} at ptr {ptr}")

		footer.write(pack(fmt, byte))
	pof0 = BytesIO()
	pof0.write(pack(f'{format}2I', int.from_bytes(TAG) if format == '>' else int.from_bytes(TAG[::-1]), len(footer.getvalue())))
	pof0.write(footer.getvalue())
	data = BytesIO()
	data.write(p.getvalue())
	data.write(pof0.getvalue())
	return data.getbuffer()