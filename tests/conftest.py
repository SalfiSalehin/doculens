import io

import pytest
from PIL import Image

from doculens.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        secret_key="x" * 40,
        cors_origins="http://localhost:5173",
        rate_limit_per_minute=1000,
        upload_dir=tmp_path / "uploads",
    )


def make_image_bytes(fmt: str = "PNG", size: tuple[int, int] = (64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buf, format=fmt)
    return buf.getvalue()


def make_pdf_bytes(pages: int = 1, encrypt: bool = False) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypt:
        writer.encrypt("pw")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
