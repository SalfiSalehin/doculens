"""Create .env from .env.example with a freshly generated secret.

Usage (PowerShell, from the project root):
    python scripts\\make_env.py            # refuses to overwrite an existing .env
    python scripts\\make_env.py --force    # overwrite
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_env(example_text: str, secret: str) -> str:
    lines = []
    for line in example_text.splitlines():
        if line.startswith("DOCULENS_SECRET_KEY="):
            line = f"DOCULENS_SECRET_KEY={secret}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing .env")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    example = args.root / ".env.example"
    target = args.root / ".env"
    if not example.exists():
        print(f"ERROR: {example} not found", file=sys.stderr)
        return 1
    if target.exists() and not args.force:
        print(".env already exists; use --force to overwrite.", file=sys.stderr)
        return 1

    content = build_env(example.read_text(encoding="utf-8"), secrets.token_urlsafe(48))
    target.write_text(content, encoding="utf-8")
    print(f"Wrote {target} (secret generated, not printed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
