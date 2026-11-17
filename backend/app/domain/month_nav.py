from datetime import date

from app.domain.calendar_util import calendar_day_count


def next_year_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def previous_year_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def month_has_ended(year: int, month: int, today: date) -> bool:
    """当前自然月尚未结束时，不能创建下月报表。"""
    last_day = calendar_day_count(year, month)
    return today >= date(year, month, last_day)


def template_day_count(year: int, month: int) -> int:
    """新建下月表按公历天数建列，不再固定铺到 31 日。"""
    return calendar_day_count(year, month)
