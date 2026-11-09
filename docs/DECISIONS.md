# Decisions

Short log of choices, newest last. Each entry: decision, why, consequence.

1. **Project location `E:\DocuLens`** instead of `C:\dev\doculens`. This is where the repo
   lives and it is not on OneDrive. Paths in the docs use `E:\DocuLens`.
2. **Phase 1 rebuilt from scratch.** The original Phase 1 zip was not available, so the
   foundation was rewritten to the same specification.
3. **A single Python package `doculens/`**, installed in editable mode. The API and the
   `ml/` scripts both import the same validation and metric code, so there is no copy-paste.
4. **Pure-ASGI middleware** for headers, size limit and rate limiting (not
   `BaseHTTPMiddleware`). It is simpler to reason about, and streamed bodies are counted too.
5. **In-memory sliding-window rate limiter** instead of Redis or slowapi. The demo runs as a
   single process. Limitation: limits reset on restart and are not shared across processes.
6. **`X-Forwarded-For` is ignored unless `DOCULENS_TRUST_PROXY=true`**, so clients cannot
   spoof their IP to dodge the rate limit.
7. **Strict CORS.** Wildcards are rejected, production origins must use https, and
   credentials are off (there are no accounts).
8. **Swagger docs only outside production.** In production `/docs` and `/openapi.json`
   return 404.
9. **Uploads:** only jpg/png/pdf. The extension, declared MIME type and magic bytes must
   all agree. Images are fully decoded with a pixel cap, and PDFs are rejected if they are
   encrypted, have too many pages, or contain JavaScript or attachment markers (best-effort).
   Files are stored under random names and purged after a TTL.
10. **Money parsing:** one separator followed by exactly 3 digits is treated as a thousands
    separator (`25.000` → 25000, as in CORD). With both separators, the last one is the
    decimal. Ambiguous strings are rejected, not guessed.
11. **Dates are parsed day-first** (SROIE is Malaysian, CORD is Indonesian).
12. **Arithmetic tolerance:** an absolute 0.02 by default. The line-item sum tolerance scales
    with the number of items.
13. **Corpus CER/WER = total edits / total reference length**, not the mean of
    per-document rates.
14. **Field F1:** exact match after normalization. A wrong value counts as both FP and FN.
15. **Docker deferred.** It is optional in the brief; we will revisit it at deploy time
    (Week 6).
