from decimal import Decimal as D

import pytest

from doculens.metrics import cer, corpus_rate, field_prf, levenshtein, wer


def test_levenshtein():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("", "abc") == 3
    assert levenshtein(["a", "b"], ["a", "b"]) == 0


def test_cer_and_wer():
    assert cer("hello", "hello").rate == 0.0
    assert cer("hello", "hallo").rate == pytest.approx(0.2)
    assert wer("total 12.50", "total 12.60").rate == pytest.approx(0.5)


def test_whitespace_and_case_normalization():
    assert cer("Total  12.50 ", "total 12.50", casefold=True).rate == 0.0
    assert cer("Total", "total").edits == 1


def test_empty_reference():
    assert cer("", "").rate == 0.0
    assert cer("", "x").rate == 1.0


def test_corpus_rate_is_length_weighted():
    # 1 edit in 10 chars + 1 edit in 2 chars = 2/12, not mean(0.1, 0.5)
    er = corpus_rate(["aaaaaaaaaa", "bb"], ["aaaaaaaaab", "bc"], cer)
    assert er.rate == pytest.approx(2 / 12)
    with pytest.raises(ValueError):
        corpus_rate(["a"], [], cer)


def test_field_prf():
    gold = [
        {"vendor": "ACME", "total": D("10.00")},
        {"vendor": "Shop", "total": D("5")},
        {"vendor": None, "total": D("7")},
    ]
    pred = [
        {"vendor": "acme ", "total": D("10")},  # both correct after normalization
        {"vendor": "Shp", "total": None},  # wrong vendor, missing total
        {"vendor": "Ghost", "total": D("7.00")},  # spurious vendor, correct total
    ]
    rep = field_prf(gold, pred, ["vendor", "total"])
    v, t = rep.per_field["vendor"], rep.per_field["total"]
    assert (v.tp, v.fp, v.fn) == (1, 2, 1)
    assert (t.tp, t.fp, t.fn) == (2, 0, 1)
    assert t.precision == 1.0 and t.recall == pytest.approx(2 / 3)
    m = rep.micro
    assert (m.tp, m.fp, m.fn) == (3, 2, 2)
    assert rep.as_dict()["micro"]["f1"] == pytest.approx(m.f1)


def test_field_prf_length_mismatch():
    with pytest.raises(ValueError):
        field_prf([{}], [], ["vendor"])
