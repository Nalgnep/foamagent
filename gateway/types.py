"""S7 type conversion (big-endian, as used on the wire).

This is deliberately independent of ``s7commplus`` so the gateway and
its tests work without that package installed. The encodings match
the library's ``values.encode/decode`` for the scalar types used here
(verified: Bool=1 byte, Int=2 bytes BE, DInt=4 bytes BE, Real=4 bytes
IEEE-754 BE). S7 String is the classic layout: byte 0 = max length,
byte 1 = actual length, then the characters, padded to max length.
Struct/UDT/array values are NOT decoded here: expose them as a
single struct point only after its layout is confirmed on the real
CPU, or expose their scalar members as separate points (recommended).
"""

from __future__ import annotations

import struct

_FORMATS = {
    "Byte": ("B", 1),
    "USInt": ("B", 1),
    "SInt": ("b", 1),
    "Char": ("b", 1),  # stored as a signed byte; decode returns a 1-char str
    "Word": ("H", 2),
    "UInt": ("H", 2),
    "Int": ("h", 2),
    "DWord": ("I", 4),
    "UDInt": ("I", 4),
    "DInt": ("i", 4),
    "Real": ("f", 4),
    "LReal": ("d", 8),
    "LWord": ("Q", 8),
    "LInt": ("q", 8),
    "ULInt": ("Q", 8),
}

SUPPORTED_TYPES = sorted(list(_FORMATS) + ["Bool", "String"])


def encode_value(type_name: str, value, string_length: int = 0) -> bytes:
    if type_name == "Bool":
        return b"\x01" if bool(value) else b"\x00"
    if type_name == "String":
        text = str(value)
        max_len = string_length or max(len(text), 1)
        if len(text) > max_len:
            raise ValueError(f"string too long for max length {max_len}")
        raw = text.encode("utf-8", errors="strict")
        return bytes([max_len, len(raw)]) + raw + b"\x00" * (max_len - len(raw))
    fmt, _size = _FORMATS[type_name]
    if type_name == "Char":
        code = ord(str(value)[0]) if isinstance(value, str) else int(value)
        return struct.pack(">b", code)
    return struct.pack(">" + fmt, value)


def decode_value(type_name: str, raw: bytes, string_length: int = 0):
    if type_name == "Bool":
        if len(raw) < 1:
            raise ValueError("empty raw value for Bool")
        return raw[0] != 0
    if type_name == "String":
        if len(raw) < 2:
            raise ValueError("empty raw value for String")
        actual = raw[1]
        return raw[2 : 2 + actual].decode("utf-8", errors="replace")
    fmt, size = _FORMATS[type_name]
    if len(raw) < size:
        raise ValueError(f"raw value too short for {type_name}: {len(raw)} < {size}")
    value = struct.unpack(">" + fmt, raw[:size])[0]
    if type_name == "Char":
        return chr(value & 0xFF)
    return value


def validate_type(type_name: str) -> None:
    if type_name not in SUPPORTED_TYPES:
        raise ValueError(f"unsupported type {type_name!r}; supported: {', '.join(SUPPORTED_TYPES)}")
