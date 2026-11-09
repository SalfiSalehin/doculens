"""Upload validation and short-lived storage.

Uploads are treated as hostile. A file is accepted only when its extension, declared
MIME type and magic bytes all agree, it is within size limits, and it parses cleanly
(image pixel count, PDF page count, no encryption, no active content markers).
Accepted files are stored under a random name and deleted after a TTL. Nothing is
ever executed.
"""

from __future__ import annotations

import io
import secrets
import time
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

Kind = Literal["image", "pdf"]

# extension -> (canonical extension, allowed MIME types, kind)
ALLOWED: dict[str, tuple[str, frozenset[str], Kind]] = {
    ".jpg": (".jpg", frozenset({"image/jpeg"}), "image"),
    ".jpeg": (".jpg", frozenset({"image/jpeg"}), "image"),
    ".png": (".png", frozenset({"image/png"}), "image"),
    ".pdf": (".pdf", frozenset({"application/pdf"}), "pdf"),
}

MAGIC: dict[str, bytes] = {
    ".jpg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".pdf": b"%PDF-",
}

PIL_FORMAT = {".jpg": "JPEG", ".png": "PNG"}

# Best-effort markers for active/embedded content. Compressed object streams can hide
# these, which is why we also never execute or render PDFs with a JS-capable viewer.
PDF_ACTIVE_MARKERS = (b"/JavaScript", b"/JS ", b"/JS(", b"/Launch", b"/EmbeddedFile", b"/XFA")


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    kind: Kind
    extension: str
    mime: str
    size: int
    safe_name: str
    width: int | None = None
    height: int | None = None
    pages: int | None = None


def _extension(filename: str) -> str:
    if not filename or "\x00" in filename:
        raise UploadRejected("bad_filename", "Missing or invalid filename.")
    ext = PurePath(filename.replace("\\", "/")).suffix.lower()
    if ext not in ALLOWED:
        raise UploadRejected("bad_extension", "Only .jpg, .jpeg, .png and .pdf files are allowed.")
    return ext


def _check_image(data: bytes, ext: str, max_pixels: int) -> tuple[int, int]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format != PIL_FORMAT[ext]:
                    raise UploadRejected("type_mismatch", "Image content does not match extension.")
                width, height = im.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise UploadRejected("too_many_pixels", "Image dimensions are too large.")
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                im.load()  # catches truncated data that verify() misses
        except UploadRejected:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise UploadRejected("too_many_pixels", "Image dimensions are too large.") from exc
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise UploadRejected("corrupt_image", "Image could not be read.") from exc
    return width, height


def _check_pdf(data: bytes, max_pages: int) -> int:
    if any(marker in data for marker in PDF_ACTIVE_MARKERS):
        raise UploadRejected("pdf_active_content", "PDFs with scripts or attachments are refused.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise UploadRejected("pdf_encrypted", "Encrypted PDFs are not supported.")
        pages = len(reader.pages)
    except UploadRejected:
        raise
    except (PdfReadError, OSError, ValueError, KeyError, TypeError) as exc:
        raise UploadRejected("corrupt_pdf", "PDF could not be read.") from exc
    if pages < 1:
        raise UploadRejected("corrupt_pdf", "PDF has no pages.")
    if pages > max_pages:
        raise UploadRejected("too_many_pages", f"PDF has more than {max_pages} pages.")
    return pages


def validate_upload(
    filename: str,
    declared_mime: str | None,
    data: bytes,
    *,
    max_bytes: int,
    max_pixels: int,
    max_pdf_pages: int,
) -> ValidatedUpload:
    ext = _extension(filename)
    canonical, mimes, kind = ALLOWED[ext]

    size = len(data)
    if size == 0:
        raise UploadRejected("empty", "File is empty.")
    if size > max_bytes:
        raise UploadRejected("too_large", "File is too large.")

    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime not in mimes:
        raise UploadRejected("bad_mime", "Declared content type does not match the file type.")

    if not data.startswith(MAGIC[canonical]):
        raise UploadRejected("type_mismatch", "File content does not match its extension.")

    safe_name = f"{secrets.token_hex(16)}{canonical}"
    if kind == "image":
        w, h = _check_image(data, canonical, max_pixels)
        return ValidatedUpload(kind, canonical, mime, size, safe_name, width=w, height=h)
    pages = _check_pdf(data, max_pdf_pages)
    return ValidatedUpload(kind, canonical, mime, size, safe_name, pages=pages)


def store_upload(upload: ValidatedUpload, data: bytes, upload_dir: Path) -> Path:
    """Write the file under its random name. Refuses to overwrite."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = (upload_dir / upload.safe_name).resolve()
    if target.parent != upload_dir.resolve():
        raise UploadRejected("bad_filename", "Invalid storage path.")
    with open(target, "xb") as fh:
        fh.write(data)
    return target


def purge_expired(upload_dir: Path, ttl_seconds: float, now: float | None = None) -> int:
    """Delete regular files older than ``ttl_seconds``. Returns how many were removed."""
    if not upload_dir.is_dir():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for path in upload_dir.iterdir():
        try:
            if (
                path.is_file()
                and not path.is_symlink()
                and now - path.stat().st_mtime > ttl_seconds
            ):
                path.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed
