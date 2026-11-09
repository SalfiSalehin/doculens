# Security

DocuLens is a portfolio demo. The basics below are in place and tested, but the app is
**not** claimed to be fully secure. Known gaps are listed honestly.

## In place

- **Secrets:** read from environment / git-ignored `.env`; `.env.example` holds
  placeholders only; `make_env.py` generates a random secret without printing it.
  Production refuses to start with a missing, placeholder or short secret.
- **Config safety checks:** no wildcard CORS; https-only origins and no DEBUG logging in
  production.
- **Log redaction:** tokens, passwords, API keys, Authorization headers, e-mails and the
  configured secret value are masked in all log records, including tracebacks.
- **HTTP hardening:** `nosniff`, `X-Frame-Options: DENY`, strict CSP for API responses,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, HSTS in production.
- **Request size limit:** checked against `Content-Length` and while streaming.
- **Rate limiting:** per client IP, sliding window; `/health` exempt.
- **Uploads treated as hostile:** extension + MIME + magic-byte agreement, size cap,
  full image decode with pixel cap (decompression bombs rejected), PDF page cap,
  encrypted PDFs rejected, PDFs with JavaScript/attachment markers rejected, random
  storage names, no overwrite, TTL purge. Uploaded files are never executed.
- **Tooling:** `ruff` (incl. bandit rules), `bandit`, `pip-audit`, `gitleaks` in CI.

## Known gaps

- Rate limiter is in-memory: resets on restart, not shared across processes/instances.
- PDF active-content detection is a byte scan; content inside compressed object streams
  can evade it. Mitigation: PDFs are only rasterised for OCR, never opened in a viewer.
- Image decoding relies on Pillow; a Pillow vulnerability would affect us. Keep it updated
  (`pip-audit`).
- No authentication (by design for the demo); anyone can use the demo within limits.
- No malware scanning of uploads.
- Behind a reverse proxy, client IPs are only correct if `DOCULENS_TRUST_PROXY=true` and the
  proxy overwrites `X-Forwarded-For`.

## Reporting

Open a GitHub issue without exploit details, or contact the maintainer privately.
