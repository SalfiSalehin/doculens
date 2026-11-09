import logging

from doculens.logging_setup import RedactingFilter, redact


def test_redacts_common_patterns():
    out = redact(
        "Authorization: Bearer abc.def.ghi password=hunter2 api_key: 'XYZ123' "
        "DOCULENS_SECRET_KEY=s3cr3t mail me@example.com"
    )
    for leaked in ("abc.def.ghi", "hunter2", "XYZ123", "s3cr3t", "me@example.com"):
        assert leaked not in out
    assert "[REDACTED]" in out and "[EMAIL]" in out


def test_redacts_exact_secret_values():
    assert "topsecretvalue" not in redact("value is topsecretvalue", ["topsecretvalue"])


def test_plain_text_untouched():
    assert redact("Processed receipt 42 in 0.8s") == "Processed receipt 42 in 0.8s"


def test_filter_on_record_with_args():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "token=%s", ("abcdef",), None)
    RedactingFilter().filter(record)
    assert record.getMessage() == "token=[REDACTED]"


def test_filter_redacts_exceptions():
    try:
        raise RuntimeError("password=hunter2")
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    RedactingFilter().filter(record)
    assert "hunter2" not in record.exc_text
