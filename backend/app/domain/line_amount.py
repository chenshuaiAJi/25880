from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.domain.money import MONEY, QTY
from app.errors import AppError

EditedField = Literal["qty", "price", "amount"]


def recalculate_line(
    quantity: Decimal | None,
    unit_price: Decimal | None,
    amount: Decimal | None,
    edited: EditedField,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """发货明细重算：改数量或单价 → 金额；直接改金额 → 反推单价。"""
    qty = _quantize_qty(quantity)
    price = _quantize_qty(unit_price)
    money = _quantize_money(amount)

    if edited == "qty":
        if qty is None:
            raise AppError("数量不能为空")
        if price is None:
            return qty, None, money
        return qty, price, (qty * price).quantize(MONEY, rounding=ROUND_HALF_UP)

    if edited == "price":
        if price is None:
            raise AppError("单价不能为空")
        if qty is None:
            return None, price, money
        return qty, price, (qty * price).quantize(MONEY, rounding=ROUND_HALF_UP)

    if money is None:
        raise AppError("金额不能为空")
    if qty is None:
        return None, price, money
    if qty == 0:
        raise AppError("数量为 0 时不能用金额反推单价")
    return qty, (money / qty).quantize(QTY, rounding=ROUND_HALF_UP), money


def parse_money_input(value: str | None, *, allow_empty: bool) -> Decimal | None:
    if value is None:
        return None
    text = value.replace(",", "").strip()
    if text == "":
        if allow_empty:
            return None
        raise AppError("金额不能为空")
    try:
        return Decimal(text).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception as error:
        raise AppError("金额格式不正确") from error


def parse_qty_input(value: str | None, *, allow_empty: bool) -> Decimal | None:
    if value is None:
        return None
    text = value.replace(",", "").strip()
    if text == "":
        if allow_empty:
            return None
        raise AppError("数量不能为空")
    try:
        return Decimal(text).quantize(QTY, rounding=ROUND_HALF_UP)
    except Exception as error:
        raise AppError("数量格式不正确") from error


def _quantize_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _quantize_qty(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(QTY, rounding=ROUND_HALF_UP)
