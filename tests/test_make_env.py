import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_env.py"
spec = importlib.util.spec_from_file_location("make_env", SCRIPT)
make_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_env)


def test_make_env(tmp_path):
    (tmp_path / ".env.example").write_text("A=1\nDOCULENS_SECRET_KEY=change-me\n")
    assert make_env.main(["--root", str(tmp_path)]) == 0
    text = (tmp_path / ".env").read_text()
    secret = text.split("DOCULENS_SECRET_KEY=")[1].strip()
    assert "A=1" in text and secret != "change-me" and len(secret) >= 48
    # refuses to overwrite without --force
    assert make_env.main(["--root", str(tmp_path)]) == 1
    assert make_env.main(["--root", str(tmp_path), "--force"]) == 0
    assert (tmp_path / ".env").read_text() != text
