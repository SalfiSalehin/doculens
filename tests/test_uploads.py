import os
import time

import pytest

from doculens.uploads import UploadRejected, purge_expired, store_upload, validate_upload
from tests.conftest import make_image_bytes, make_pdf_bytes

LIMITS = {"max_bytes": 5 * 1024 * 1024, "max_pixels": 10_000_000, "max_pdf_pages": 3}


def rejected(code, *args, **kw):
    with pytest.raises(UploadRejected) as exc:
        validate_upload(*args, **{**LIMITS, **kw})
    assert exc.value.code == code


def test_valid_png():
    up = validate_upload("r.png", "image/png", make_image_bytes("PNG"), **LIMITS)
    assert up.kind == "image" and up.width == 64 and up.height == 48
    assert up.safe_name.endswith(".png") and len(up.safe_name) == 36


def test_valid_jpeg_normalizes_extension():
    up = validate_upload("R.JPEG", "image/jpeg", make_image_bytes("JPEG"), **LIMITS)
    assert up.extension == ".jpg"


def test_random_names_differ():
    data = make_image_bytes()
    a = validate_upload("a.png", "image/png", data, **LIMITS)
    b = validate_upload("a.png", "image/png", data, **LIMITS)
    assert a.safe_name != b.safe_name


def test_valid_pdf():
    up = validate_upload("r.pdf", "application/pdf", make_pdf_bytes(2), **LIMITS)
    assert up.kind == "pdf" and up.pages == 2


@pytest.mark.parametrize("name", ["", "evil.exe", "x.svg", "x.html", "noext", "a.png\x00.exe"])
def test_bad_names(name):
    with pytest.raises(UploadRejected):
        validate_upload(name, "image/png", make_image_bytes(), **LIMITS)


def test_empty():
    rejected("empty", "r.png", "image/png", b"")


def test_too_large():
    rejected("too_large", "r.png", "image/png", make_image_bytes(), max_bytes=10)


def test_mime_mismatch():
    rejected("bad_mime", "r.png", "image/jpeg", make_image_bytes("PNG"))


def test_magic_mismatch_jpeg_named_png():
    rejected("type_mismatch", "r.png", "image/png", make_image_bytes("JPEG"))


def test_script_disguised_as_png():
    rejected("type_mismatch", "r.png", "image/png", b"<?php system($_GET['c']); ?>")


def test_truncated_png():
    data = make_image_bytes("PNG", (300, 300))
    rejected("corrupt_image", "r.png", "image/png", data[: len(data) // 2])


def test_too_many_pixels():
    rejected("too_many_pixels", "r.png", "image/png", make_image_bytes(size=(200, 200)),
             max_pixels=30_000)  # fmt: skip


def test_pdf_too_many_pages():
    rejected("too_many_pages", "r.pdf", "application/pdf", make_pdf_bytes(5))


def test_pdf_encrypted():
    rejected("pdf_encrypted", "r.pdf", "application/pdf", make_pdf_bytes(1, encrypt=True))


def test_pdf_with_javascript():
    data = make_pdf_bytes(1).replace(b"%%EOF", b"/JavaScript (app.alert(1))\n%%EOF")
    rejected("pdf_active_content", "r.pdf", "application/pdf", data)


def test_pdf_garbage():
    rejected("corrupt_pdf", "r.pdf", "application/pdf", b"%PDF-1.7\nnot really a pdf")


def test_store_and_purge(tmp_path):
    data = make_image_bytes()
    up = validate_upload("r.png", "image/png", data, **LIMITS)
    path = store_upload(up, data, tmp_path)
    assert path.read_bytes() == data and path.parent == tmp_path.resolve()
    with pytest.raises(FileExistsError):
        store_upload(up, data, tmp_path)

    old = time.time() - 3600
    os.utime(path, (old, old))
    fresh = store_upload(validate_upload("r.png", "image/png", data, **LIMITS), data, tmp_path)
    assert purge_expired(tmp_path, ttl_seconds=600) == 1
    assert not path.exists() and fresh.exists()


def test_purge_missing_dir(tmp_path):
    assert purge_expired(tmp_path / "nope", 60) == 0
