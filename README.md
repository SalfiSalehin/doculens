# DocuLens

Reads a receipt or invoice image and returns structured data: vendor, date, line items,
subtotal, tax and total. Each field gets a confidence score, the arithmetic is checked, and
a review screen lets you fix mistakes and export JSON or CSV.

> **Status:** Phase 1 (foundation) only. No extraction results yet, so no metrics are
> reported. Every number added to this README later will link to a saved evaluation run.

## Pipeline (planned)

```
upload -> clean up image (OpenCV) -> OCR -> LayoutLMv3 + rules -> confidence
       -> arithmetic/date checks -> review UI -> export JSON / CSV
```

## What exists now

| Part | Where |
|---|---|
| Secure FastAPI skeleton (config checks, log redaction, security headers, CORS allowlist, size limit, rate limit, `/health`) | `doculens/api/`, `doculens/config.py`, `doculens/logging_setup.py` |
| Upload validation and TTL storage | `doculens/uploads.py` |
| Money / totals / line-item / date checks | `doculens/validation/rules.py` |
| CER, WER, field P/R/F1 | `doculens/metrics.py` |
| `.env` generator, GPU check | `scripts/` |
| CI (ruff, pytest, bandit, pip-audit, gitleaks) | `.github/workflows/ci.yml` |

## Quick start (Windows PowerShell)

See [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md). In short:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts\make_env.py
pytest
uvicorn doculens.api.main:create_app --factory --reload
```

## Datasets and licences

The datasets are not committed. CORD v2 (CC BY 4.0) and SROIE (ICDAR 2019 terms) will be
downloaded by script in Week 2. The LayoutLMv3 weights are licensed for non-commercial
use only, which is fine for this portfolio demo.

## Docs

- [docs/DECISIONS.md](docs/DECISIONS.md): design decisions
- [SECURITY.md](SECURITY.md): what is protected and the known gaps

## License

MIT for the code. Datasets and model weights keep their own licences.
