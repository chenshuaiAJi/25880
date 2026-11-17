import calendar


def calendar_day_count(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]
