from datetime import date
from decimal import Decimal


def as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("期望整数")


def as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    raise TypeError("期望金额")


def as_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return as_decimal(value)


def as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("期望字符串")


def as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return as_str(value)


def as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    raise TypeError("期望日期")


def as_optional_date(value: object) -> date | None:
    if value is None:
        return None
    return as_date(value)


def like_pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
