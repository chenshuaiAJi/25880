from decimal import Decimal, ROUND_HALF_UP

from app.domain.money import MONEY


def month_balance(opening: Decimal, remit_total: Decimal, ship_total: Decimal) -> Decimal:
    """月末余额 = 上月余额 + 本月汇款总额 − 本月发货总额。"""
    return (opening + remit_total - ship_total).quantize(MONEY, rounding=ROUND_HALF_UP)


def sum_money(amounts: list[Decimal]) -> Decimal:
    total = sum(amounts, Decimal("0"))
    return total.quantize(MONEY, rounding=ROUND_HALF_UP)
