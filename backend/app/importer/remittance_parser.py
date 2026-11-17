"""汇款月表：第 1 行日期，第 2 行把每天拆成汇款、发货。空行不是门店。"""

from decimal import Decimal

from xlrd.sheet import Sheet

from app.domain.balance import month_balance, sum_money
from app.domain.money import money_from_excel
from app.importer.models import (
    ParsedCell,
    ParsedRemittance,
    ParsedRemittanceRow,
    ParseWarning,
    cell_text,
    workbook_sheet,
)
from pathlib import Path


def parse_remittance_workbook(path: Path) -> ParsedRemittance:
    sheet = workbook_sheet(path)
    header_row = _find_header_row(sheet)
    total_cols = _total_columns(sheet, header_row)
    first_total = min(total_cols.values())
    span = first_total - 2
    if span <= 0 or span % 2 != 0:
        raise ValueError(f"汇款表日期列无法对齐：{path.name}")
    day_count = span // 2
    warnings: list[ParseWarning] = []
    rows: list[ParsedRemittanceRow] = []
    for row_index in range(header_row + 2, sheet.nrows):
        raw_name = cell_text(sheet.cell_value(row_index, 0))
        if raw_name == "" or raw_name == "门店编号及名称":
            continue
        opening = money_from_excel(sheet.cell_value(row_index, 1))
        if opening is None:
            opening = Decimal("0.00")
        cells: list[ParsedCell] = []
        for day in range(1, day_count + 1):
            remit_col = 2 + (day - 1) * 2
            ship_col = remit_col + 1
            remit_amount = _read_money(sheet, row_index, remit_col, raw_name, day, "汇款", warnings)
            ship_amount = _read_money(sheet, row_index, ship_col, raw_name, day, "发货", warnings)
            if remit_amount is not None:
                cells.append(ParsedCell(day, "remit", remit_amount))
            if ship_amount is not None:
                cells.append(ParsedCell(day, "ship", ship_amount))
        excel_remit = money_from_excel(sheet.cell_value(row_index, total_cols["remit"]))
        excel_ship = money_from_excel(sheet.cell_value(row_index, total_cols["ship"]))
        excel_balance = money_from_excel(sheet.cell_value(row_index, total_cols["balance"]))
        _check_totals(raw_name, opening, cells, excel_remit, excel_ship, excel_balance, warnings)
        rows.append(
            ParsedRemittanceRow(
                row_index=row_index,
                raw_name=raw_name,
                opening_balance=opening,
                cells=cells,
                excel_remit_total=excel_remit,
                excel_ship_total=excel_ship,
                excel_balance=excel_balance,
            )
        )
    return ParsedRemittance(
        sheet_name=sheet.name,
        day_count=day_count,
        rows=rows,
        warnings=warnings,
    )


def _find_header_row(sheet: Sheet) -> int:
    limit = min(sheet.nrows, 6)
    for row_index in range(limit):
        if "门店" in cell_text(sheet.cell_value(row_index, 0)):
            return row_index
    raise ValueError("找不到「门店编号及名称」表头")


def _total_columns(sheet: Sheet, header_row: int) -> dict[str, int]:
    found: dict[str, int] = {}
    for col in range(sheet.ncols):
        header = cell_text(sheet.cell_value(header_row, col))
        if "汇款总额" in header:
            found["remit"] = col
        elif "发货总额" in header:
            found["ship"] = col
        elif "余额" in header and col > 1:
            found["balance"] = col
    if set(found) != {"remit", "ship", "balance"}:
        raise ValueError("汇款表缺少总额或余额列")
    return found


def _read_money(
    sheet: Sheet,
    row_index: int,
    col: int,
    raw_name: str,
    day: int,
    kind_label: str,
    warnings: list[ParseWarning],
):
    value = sheet.cell_value(row_index, col)
    parsed = money_from_excel(value)
    if parsed is None and value not in ("", None):
        warnings.append(
            ParseWarning(
                code="CELL_NOT_NUMBER",
                message=f"{raw_name} {day}日{kind_label}不是数值：{cell_text(value)}",
            )
        )
    return parsed


def _check_totals(
    raw_name: str,
    opening: Decimal,
    cells: list[ParsedCell],
    excel_remit: Decimal | None,
    excel_ship: Decimal | None,
    excel_balance: Decimal | None,
    warnings: list[ParseWarning],
) -> None:
    remit_total = sum_money([cell.amount for cell in cells if cell.kind == "remit"])
    ship_total = sum_money([cell.amount for cell in cells if cell.kind == "ship"])
    if excel_remit is not None and excel_remit != remit_total:
        warnings.append(
            ParseWarning(
                code="TOTAL_MISMATCH",
                message=f"{raw_name} 汇款总额不一致：表内 {excel_remit}，按日合计 {remit_total}",
            )
        )
    if excel_ship is not None and excel_ship != ship_total:
        warnings.append(
            ParseWarning(
                code="TOTAL_MISMATCH",
                message=f"{raw_name} 发货总额不一致：表内 {excel_ship}，按日合计 {ship_total}",
            )
        )
    if excel_balance is not None:
        computed = month_balance(opening, remit_total, ship_total)
        if computed != excel_balance:
            warnings.append(
                ParseWarning(
                    code="BALANCE_MISMATCH",
                    message=f"{raw_name} 余额不一致：表内 {excel_balance}，按公式 {computed}",
                )
            )
