from fastapi import Request
from fastapi.testclient import TestClient

from doculens.api.main import create_app
from doculens.api.middleware import SlidingWindowLimiter


def client_for(settings) -> TestClient:
    return TestClient(create_app(settings))


def test_health(settings):
    r = client_for(settings).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_security_headers(settings):
    r = client_for(settings).get("/health")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "strict-transport-security" not in h  # only in production


def test_hsts_in_production(settings):
    prod = settings.model_copy(
        update={"env": "production", "cors_origins": "https://demo.example.com"}
    )
    r = client_for(prod).get("/health")
    assert "strict-transport-security" in r.headers


def test_docs_disabled_in_production(settings):
    prod = settings.model_copy(
        update={"env": "production", "cors_origins": "https://demo.example.com"}
    )
    c = client_for(prod)
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_headers_on_404(settings):
    r = client_for(settings).get("/nope")
    assert r.status_code == 404
    assert r.headers["x-content-type-options"] == "nosniff"


def test_cors_allows_listed_origin(settings):
    r = client_for(settings).get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_other_origin(settings):
    r = client_for(settings).get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers


def _app_with_echo(settings):
    app = create_app(settings)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"n": len(await request.body())}

    return app


def test_body_size_limit_content_length(settings):
    small = settings.model_copy(update={"max_upload_mb": 1})
    c = TestClient(_app_with_echo(small))
    assert c.post("/echo", content=b"a" * 1000).json() == {"n": 1000}
    r = c.post("/echo", content=b"a" * (small.max_request_bytes + 1))
    assert r.status_code == 413
    assert r.headers["x-content-type-options"] == "nosniff"


def test_body_size_limit_streamed(settings):
    small = settings.model_copy(update={"max_upload_mb": 1})
    c = TestClient(_app_with_echo(small))

    def chunks():
        for _ in range(40):
            yield b"a" * 32 * 1024  # 1.25 MiB total, no Content-Length

    r = c.post("/echo", content=chunks())
    assert r.status_code == 413


def test_rate_limit(settings):
    limited = settings.model_copy(update={"rate_limit_per_minute": 3})
    c = client_for(limited)
    codes = [c.get("/nope").status_code for _ in range(4)]
    assert codes[:3] == [404, 404, 404]
    assert codes[3] == 429
    # health stays reachable for uptime checks
    assert c.get("/health").status_code == 200


def test_limiter_window_slides():
    now = [0.0]
    lim = SlidingWindowLimiter(2, 60.0, clock=lambda: now[0])
    assert lim.hit("a")[0] and lim.hit("a")[0]
    allowed, retry = lim.hit("a")
    assert not allowed and 1 <= retry <= 60
    assert lim.hit("b")[0]  # other clients unaffected
    now[0] = 61.0
    assert lim.hit("a")[0]


def test_limiter_bounded_memory():
    now = [0.0]
    lim = SlidingWindowLimiter(1, 60.0, clock=lambda: now[0], max_keys=10)
    for i in range(100):
        lim.hit(f"ip{i}")
    assert len(lim._hits) <= 10
