from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.balance import month_balance
from app.importer.filenames import (
    list_workbooks,
    parse_remittance_filename,
    parse_shipment_filename,
    shipment_span_end,
)
from app.importer.remittance_parser import parse_remittance_workbook
from app.importer.shipment_parser import parse_shipment_workbook

DATA = Path(__file__).resolve().parents[2] / "file" / "2026年财务总报表" / "2026年财务总报表"


def test_filename_batch_and_cross_month() -> None:
    batch = parse_shipment_filename("1-2 (4).xls", 2026, 10)
    assert batch.batch_no == 4
    assert batch.biz_date == date(2026, 10, 1)
    plain = parse_shipment_filename("15-16.xls", 2026, 11)
    assert plain.batch_no == 0
    assert plain.biz_date == date(2026, 11, 15)
    cross = parse_shipment_filename("31-1.xls", 2026, 10)
    assert cross.biz_date == date(2026, 10, 31)
    letter = parse_shipment_filename("1-2B.xls", 2026, 1)
    assert letter.batch_label == "B"
    assert letter.biz_date == date(2026, 1, 1)
    typo = parse_shipment_filename("3-+4.xls", 2026, 2)
    assert typo.batch_no == 0
    assert typo.biz_date == date(2026, 2, 3)
    assert parse_remittance_filename("11月汇款明细总.xls", 2026) == (2026, 11)


def test_skip_non_xls() -> None:
    listed = list_workbooks(DATA)
    ignored_names = {Path(item).name for item in listed.ignored}
    assert "ebhelper.exe" in ignored_names
    assert "1-2.lnk" in ignored_names
    assert "1-2" in ignored_names
    assert len(listed.remittances) == 12
    assert len(listed.shipments) >= 640


def test_balance_formula() -> None:
    assert month_balance(Decimal("-5514.27"), Decimal("20042.00"), Decimal("10935.92")) == Decimal("3591.81")


def test_january_remittance_matches_excel() -> None:
    parsed = parse_remittance_workbook(DATA / "新汇款明细" / "1月汇款明细总.xls")
    assert parsed.day_count == 31
    assert len(parsed.rows) == 20
    row = next(item for item in parsed.rows if item.raw_name == "021东大里-李大进")
    assert row.opening_balance == Decimal("-5514.27")
    cells = {(cell.day, cell.kind): cell.amount for cell in row.cells}
    assert (1, "remit") not in cells
    assert cells[(1, "ship")] == Decimal("633.00")
    assert cells[(2, "ship")] == Decimal("1046.64")
    assert row.excel_remit_total == Decimal("20042.00")
    assert row.excel_ship_total == Decimal("10935.92")
    assert row.excel_balance == Decimal("3591.81")
    assert not any("021东大里-李大进" in item.message for item in parsed.warnings)


def test_shipment_order_amounts() -> None:
    location = parse_shipment_filename("1-2.xls", 2026, 1)
    parsed = parse_shipment_workbook(DATA / "发货单" / "1月份" / "1-2.xls", location.biz_date, shipment_span_end(location))
    assert parsed.conflicts == []
    first = parsed.orders[0]
    assert first.customer_raw_name == "陈立君会员店-陈立君会员店"
    assert first.lines[0].product_name == "去皮大五花肉15kg/件"
    assert first.lines[0].order_qty == Decimal("30")
    assert first.lines[0].unit_price == Decimal("21.2")
    assert first.lines[0].amount == Decimal("636.00")
    assert sum((line.amount or Decimal("0") for line in first.lines), Decimal("0")) == Decimal("8894.00")
    second = parsed.orders[1]
    assert second.customer_raw_name == "李大进-东大里店"
    assert sum((line.amount or Decimal("0") for line in second.lines), Decimal("0")) == Decimal("633.00")


def test_cell_date_conflict_does_not_change_biz_date() -> None:
    location = parse_shipment_filename("1-2 (1).xls", 2026, 1)
    parsed = parse_shipment_workbook(
        DATA / "发货单" / "1月份" / "1-2 (1).xls",
        location.biz_date,
        shipment_span_end(location),
    )
    assert location.biz_date == date(2026, 1, 1)
    assert parsed.conflicts
    assert parsed.conflicts[0].parsed_cell_date == date(2026, 2, 1)
    assert parsed.conflicts[0].biz_date == date(2026, 1, 1)


def test_november_file_has_no_date_conflict() -> None:
    location = parse_shipment_filename("15-16.xls", 2026, 11)
    parsed = parse_shipment_workbook(
        DATA / "发货单" / "11月份" / "15-16.xls",
        location.biz_date,
        shipment_span_end(location),
    )
    assert parsed.conflicts == []
    assert parsed.orders[0].customer_raw_name == "李星星-大庙村店"
    assert parsed.orders[0].lines[0].amount == Decimal("29.00")
