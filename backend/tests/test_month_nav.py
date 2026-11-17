from datetime import date

from app.domain.month_nav import month_has_ended, next_year_month, template_day_count


def test_next_month_rolls_year() -> None:
    assert next_year_month(2026, 12) == (2027, 1)
    assert next_year_month(2026, 11) == (2026, 12)


def test_month_end_gate() -> None:
    assert month_has_ended(2026, 10, date(2026, 10, 31)) is True
    assert month_has_ended(2026, 10, date(2026, 10, 30)) is False
    assert month_has_ended(2026, 11, date(2026, 11, 16)) is False


def test_february_leap_day_count() -> None:
    assert template_day_count(2024, 2) == 29
    assert template_day_count(2026, 2) == 28
    assert template_day_count(2027, 1) == 31
