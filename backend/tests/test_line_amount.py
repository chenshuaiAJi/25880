from decimal import Decimal

import pytest

from app.domain.line_amount import recalculate_line
from app.errors import AppError


def test_change_price_updates_amount() -> None:
    qty, price, amount = recalculate_line(Decimal("30"), Decimal("21.2"), Decimal("0"), "price")
    assert qty == Decimal("30.0000")
    assert price == Decimal("21.2000")
    assert amount == Decimal("636.00")


def test_change_qty_updates_amount() -> None:
    qty, price, amount = recalculate_line(Decimal("15"), Decimal("12.6"), None, "qty")
    assert amount == Decimal("189.00")
    assert qty == Decimal("15.0000")


def test_change_amount_reverse_price() -> None:
    qty, price, amount = recalculate_line(Decimal("30"), Decimal("20"), Decimal("900"), "amount")
    assert amount == Decimal("900.00")
    assert price == Decimal("30.0000")


def test_change_amount_with_zero_qty_rejected() -> None:
    with pytest.raises(AppError, match="数量为 0"):
        recalculate_line(Decimal("0"), Decimal("10"), Decimal("100"), "amount")
