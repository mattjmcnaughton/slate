"""Images attached to an assistant message: validated, re-encoded, never stored.

Checked by magic bytes, decoded under a pixel cap, and re-encoded to a JPEG of at
most 1568 px on the long side, which drops EXIF and other metadata. Only the
re-encoded bytes reach the model, for one turn. Callers run this in a worker
thread, after authentication.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_EDGE = 1568
MAX_PIXELS = 40_000_000


class ImageRejectedError(ValueError):
    pass


def _format(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def normalize(data: bytes) -> bytes:
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageRejectedError("Each image must be 5 MB or smaller.")
    kind = _format(data)
    if kind is None:
        raise ImageRejectedError("Attach a JPEG, PNG, or WebP image.")
    try:
        with Image.open(io.BytesIO(data), formats=[kind]) as image:
            if image.size[0] * image.size[1] > MAX_PIXELS:
                raise ImageRejectedError("That image is too large to read.")
            image.load()
            rgb = image.convert("RGB")
            rgb.thumbnail((MAX_EDGE, MAX_EDGE))
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=85)
    except ImageRejectedError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageRejectedError("That image could not be read.") from None
    return out.getvalue()


def normalize_all(images: list[bytes]) -> list[bytes]:
    if len(images) > MAX_IMAGES:
        raise ImageRejectedError("Attach at most 4 images.")
    return [normalize(data) for data in images]
