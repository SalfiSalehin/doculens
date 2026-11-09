from datetime import date
from decimal import Decimal as D

import pytest

from doculens.validation import (
    LineItem,
    check_date,
    check_line_items,
    check_totals,
    parse_date,
    parse_money,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12.50", D("12.50")),
        ("$1,234.56", D("1234.56")),
        ("1.234,56", D("1234.56")),
        ("RM 12.50", D("12.50")),
        ("Rp 25.000", D("25000")),
        ("25,000", D("25000")),
        ("1.250.000", D("1250000")),
        ("12,5", D("12.5")),
        ("1234", D("1234")),
        ("(5.00)", D("-5.00")),
        ("-5.00", D("-5.00")),
        ("5.00-", D("-5.00")),
        (".50", D("0.50")),
        (7, D("7")),
        (D("3.3"), D("3.3")),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", [None, "", "abc", "12.5.6.7", "1,23,456", "12.3456", "1.2,3.4"])
def test_parse_money_rejects(text):
    assert parse_money(text) is None


def test_totals_pass_with_rounding():
    r = check_totals(D("10.00"), D("0.60"), D("10.61"))
    assert r.passed


def test_totals_fail():
    r = check_totals(D("10.00"), D("0.60"), D("11.00"))
    assert r.status == "fail" and r.expected == D("10.60")


def test_totals_with_discount_and_service():
    assert check_totals(D("100"), D("10"), D("105"), discount=D("10"), service=D("5")).passed


def test_totals_tax_optional():
    assert check_totals(D("50"), None, D("50")).passed


def test_totals_skipped():
    assert check_totals(None, D("1"), D("2")).status == "skipped"


def test_line_items():
    items = [
        LineItem("Tea", D("2"), D("1.50"), D("3.00")),
        LineItem("Cake", D("1"), D("4.25"), D("4.25")),
    ]
    results = check_line_items(items, D("7.25"))
    assert [r.status for r in results] == ["pass", "pass", "pass"]


def test_line_items_failures():
    items = [LineItem("Tea", D("2"), D("1.50"), D("4.00")), LineItem("X", amount=D("1"))]
    results = check_line_items(items, D("9.99"))
    assert [r.status for r in results] == ["fail", "skipped", "fail"]


def test_line_items_sum_skipped_when_amount_missing():
    results = check_line_items([LineItem("Tea")], D("1"))
    assert results[-1].status == "skipped"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("25/12/2018", date(2018, 12, 25)),
        ("05/03/2019", date(2019, 3, 5)),  # day-first
        ("2019-03-05", date(2019, 3, 5)),
        ("05-03-19", date(2019, 3, 5)),
        ("5 Mar 2019", date(2019, 3, 5)),
        ("Mar 5, 2019", date(2019, 3, 5)),
        ("05.03.2019.", date(2019, 3, 5)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", [None, "", "31/02/2019", "hello", "13/13/2019"])
def test_parse_date_rejects(text):
    assert parse_date(text) is None


def test_check_date():
    today = date(2026, 1, 1)
    assert check_date("01/06/2025", today=today).passed
    assert check_date("01/06/2027", today=today).status == "fail"
    assert check_date("01/06/1980", today=today).status == "fail"
    assert check_date("garbage", today=today).status == "fail"
    assert check_date(None, today=today).status == "skipped"
