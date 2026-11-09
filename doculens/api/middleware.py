"""Pure-ASGI middleware: security headers, request size limit, rate limiting."""

from __future__ import annotations

import json
import math
import time
from collections import deque
from collections.abc import Callable, Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send


async def send_json_error(
    send: Send, status: int, detail: str, extra_headers: Iterable[tuple[bytes, bytes]] = ()
) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *extra_headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------- headers

API_CSP = b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """Adds conservative security headers to every HTTP response."""

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        is_docs = path.startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}

                def add(name: bytes, value: bytes) -> None:
                    if name not in present:
                        headers.append((name, value))

                add(b"x-content-type-options", b"nosniff")
                add(b"x-frame-options", b"DENY")
                add(b"referrer-policy", b"no-referrer")
                add(b"permissions-policy", b"camera=(), microphone=(), geolocation=()")
                add(b"cross-origin-opener-policy", b"same-origin")
                add(b"cross-origin-resource-policy", b"same-site")
                add(b"cache-control", b"no-store")
                # Swagger UI (dev only) loads CDN assets, so it gets no strict CSP.
                if not is_docs:
                    add(b"content-security-policy", API_CSP)
                if self.hsts:
                    add(b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --------------------------------------------------------------------------- size limit


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects requests whose body exceeds ``max_bytes``.

    Checks ``Content-Length`` up front and also counts streamed bytes, so chunked
    uploads without a length header cannot bypass the limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await send_json_error(send, 400, "Invalid Content-Length header.")
                    return
                if declared < 0:
                    await send_json_error(send, 400, "Invalid Content-Length header.")
                    return
                if declared > self.max_bytes:
                    await send_json_error(send, 413, "Request body too large.")
                    return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await send_json_error(send, 413, "Request body too large.")


# --------------------------------------------------------------------------- rate limit


class SlidingWindowLimiter:
    """In-memory sliding-window limiter (single process; fine for a demo)."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``."""
        now = self.clock()
        cutoff = now - self.window
        bucket = self._hits.get(key)
        if bucket is None:
            if len(self._hits) >= self.max_keys:
                self._evict(cutoff)
            bucket = self._hits[key] = deque()
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry = max(1, math.ceil(bucket[0] + self.window - now))
            return False, retry
        bucket.append(now)
        return True, 0

    def _evict(self, cutoff: float) -> None:
        for k in [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:
            # Still full: drop the oldest-touched keys.
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])
            for k in oldest[: len(oldest) // 2]:
                del self._hits[k]


def client_key(scope: Scope, trust_proxy: bool) -> str:
    if trust_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limiter: SlidingWindowLimiter,
        exempt_paths: Iterable[str] = (),
        trust_proxy: bool = False,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.exempt = frozenset(exempt_paths)
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        if scope.get("path", "") in self.exempt:
            await self.app(scope, receive, send)
            return
        allowed, retry_after = self.limiter.hit(client_key(scope, self.trust_proxy))
        if not allowed:
            await send_json_error(
                send,
                429,
                "Too many requests. Please slow down.",
                [(b"retry-after", str(retry_after).encode())],
            )
            return
        await self.app(scope, receive, send)
