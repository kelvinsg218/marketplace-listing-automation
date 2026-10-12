import pytest

from mla.core.units import ParseError, format_money, format_scaled, parse_money, parse_scaled


@pytest.mark.parametrize("text, cents", [
    ("129,90", 12990), ("R$ 1.234,56", 123456), ("10", 1000), ("10.5", 1050),
    ("1.000.000", 100000000), ("", None), ("  ", None), ("0,005", 1),
])
def test_parse_money(text, cents):
    assert parse_money(text) == cents


def test_parse_money_rejects_garbage():
    with pytest.raises(ParseError):
        parse_money("1,2,3")


@pytest.mark.parametrize("cents, text", [(12990, "R$ 129,90"), (123456, "R$ 1.234,56"), (5, "R$ 0,05"), (None, "")])
def test_format_money(cents, text):
    assert format_money(cents) == text


def test_scaled_roundtrip():
    assert parse_scaled("20,5", 10) == 205
    assert format_scaled(205, 10) == "20,5"
    assert format_scaled(200, 10) == "20"
    assert parse_scaled("", 10) is None
