"""Bounded metadata readers for images and WAV audio.

These functions inspect headers only. They do not decode pixels, run OCR, or
transcribe audio, so they cannot claim to understand media content.
"""

from __future__ import annotations

import base64
import binascii
import struct
from typing import Any

MAX_BYTES = 2_000_000

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _bytes(payload: dict[str, Any], key: str) -> bytes:
    value = payload.get("value", payload.get(key))
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith("data:"):
            _, _, text = text.partition(",")
        try:
            data = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("media must be valid base64") from exc
    else:
        raise ValueError("media must be a base64 string or bytes")
    if not data:
        raise ValueError("media is empty")
    if len(data) > MAX_BYTES:
        raise ValueError(f"media exceeds {MAX_BYTES} bytes")
    return data


def image_info(payload: dict[str, Any]) -> dict[str, Any]:
    data = _bytes(payload, "image")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 26:
        width, height = struct.unpack(">II", data[16:24])
        return {
            "format": "png",
            "width": width,
            "height": height,
            "bytes": len(data),
            "bit_depth": data[24],
            "color_type": data[25],
        }
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return {
            "format": "gif",
            "version": data[:6].decode("ascii"),
            "width": width,
            "height": height,
            "bytes": len(data),
        }
    if data.startswith(b"BM") and len(data) >= 26:
        width, height = struct.unpack("<ii", data[18:26])
        return {
            "format": "bmp",
            "width": abs(width),
            "height": abs(height),
            "bytes": len(data),
        }
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = int.from_bytes(data[index + 2 : index + 4], "big")
            if length < 2:
                raise ValueError("invalid JPEG segment length")
            if marker in _JPEG_SOF:
                height = int.from_bytes(data[index + 5 : index + 7], "big")
                width = int.from_bytes(data[index + 7 : index + 9], "big")
                return {
                    "format": "jpeg",
                    "width": width,
                    "height": height,
                    "components": data[index + 9],
                    "bytes": len(data),
                }
            index += 2 + length
        raise ValueError("JPEG has no start-of-frame segment")
    raise ValueError("unsupported image format (png, gif, bmp, jpeg)")


def wav_info(payload: dict[str, Any]) -> dict[str, Any]:
    data = _bytes(payload, "audio")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    index = 12
    fmt: dict[str, int] | None = None
    data_size: int | None = None
    while index + 8 <= len(data):
        chunk = data[index : index + 4]
        size = int.from_bytes(data[index + 4 : index + 8], "little")
        body = data[index + 8 : index + 8 + size]
        if chunk == b"fmt " and len(body) >= 16:
            audio_format, channels, sample_rate, byte_rate, block_align, bits = (
                struct.unpack("<HHIIHH", body[:16])
            )
            fmt = {
                "audio_format": audio_format,
                "channels": channels,
                "sample_rate": sample_rate,
                "byte_rate": byte_rate,
                "block_align": block_align,
                "bits_per_sample": bits,
            }
        elif chunk == b"data":
            data_size = size
        index += 8 + size + (size & 1)
    if fmt is None or data_size is None:
        raise ValueError("WAV is missing fmt or data chunk")
    duration = data_size / fmt["byte_rate"] if fmt["byte_rate"] else 0.0
    return {
        "format": "wav",
        **fmt,
        "data_bytes": data_size,
        "duration_s": round(duration, 6),
        "bytes": len(data),
    }
