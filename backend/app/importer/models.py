from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

CellKind = Literal["remit", "ship"]


@dataclass
class ParseWarning:
    code: str
    message: str


@dataclass
class ParsedCell:
    day: int
    kind: CellKind
    amount: Decimal


@dataclass
class ParsedRemittanceRow:
    row_index: int
    raw_name: str
    opening_balance: Decimal
    cells: list[ParsedCell]
    excel_remit_total: Decimal | None
    excel_ship_total: Decimal | None
    excel_balance: Decimal | None


@dataclass
class ParsedRemittance:
    sheet_name: str
    day_count: int
    rows: list[ParsedRemittanceRow]
    warnings: list[ParseWarning] = field(default_factory=list)


@dataclass
class ParsedLine:
    product_name: str
    unit: str | None
    order_qty: Decimal | None
    ship_qty: Decimal | None
    gift_qty: Decimal | None
    weight_total: Decimal | None
    actual_weight: Decimal | None
    gift_weight: Decimal | None
    actual_qty: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass
class ParsedOrder:
    customer_raw_name: str
    market_name: str | None = None
    phone: str | None = None
    address: str | None = None
    price_ratio: str | None = None
    ship_date_text: str | None = None
    lines: list[ParsedLine] = field(default_factory=list)
    excel_total_amount: Decimal | None = None


@dataclass
class ParsedConflict:
    cell_text: str
    parsed_cell_date: date | None
    biz_date: date


@dataclass
class ParsedShipment:
    sheet_name: str
    orders: list[ParsedOrder]
    conflicts: list[ParsedConflict]
    warnings: list[ParseWarning] = field(default_factory=list)


def cell_text(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def workbook_sheet(path: Path):
    import xlrd

    book = xlrd.open_workbook(str(path), formatting_info=False)
    return book.sheet_by_index(0)
