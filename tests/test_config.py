import pytest
from pydantic import ValidationError

from doculens.config import Settings


def make(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_defaults_are_dev_and_safe():
    s = make()
    assert s.env == "development"
    assert s.cors_origin_list == ["http://localhost:5173"]
    assert s.max_request_bytes > s.max_upload_bytes


def test_secret_not_in_repr():
    s = make(secret_key="supersecretvalue1234567890abcdefgh")
    assert "supersecretvalue" not in repr(s)


@pytest.mark.parametrize("origins", ["*", "https://*.example.com", "example.com", "http://a.com/"])
def test_bad_cors_rejected(origins):
    with pytest.raises(ValidationError):
        make(cors_origins=origins)


def test_cors_list_parsing():
    s = make(cors_origins=" http://a.com , http://b.com ")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


@pytest.mark.parametrize("secret", ["", "change-me", "short"])
def test_production_requires_real_secret(secret):
    with pytest.raises(ValidationError):
        make(env="production", secret_key=secret, cors_origins="https://demo.example.com")


def test_production_requires_https_cors():
    with pytest.raises(ValidationError):
        make(env="production", secret_key="k" * 40, cors_origins="http://demo.example.com")


def test_production_rejects_debug_logging():
    with pytest.raises(ValidationError):
        make(
            env="production",
            secret_key="k" * 40,
            cors_origins="https://demo.example.com",
            log_level="DEBUG",
        )


def test_valid_production():
    s = make(env="production", secret_key="k" * 40, cors_origins="https://demo.example.com")
    assert s.is_production


def test_env_vars_are_read(monkeypatch):
    monkeypatch.setenv("DOCULENS_MAX_UPLOAD_MB", "5")
    assert make().max_upload_mb == 5
