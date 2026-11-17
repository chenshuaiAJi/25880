from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from psycopg import Connection

from app.domain.month_nav import previous_year_month
from app.errors import AppError
from app.readers.remittances import get_remittance_sheet
from app.readers.values import as_int, as_str


def export_remittance_xlsx(conn: Connection, year: int, month: int) -> tuple[bytes, str]:
    sheet = get_remittance_sheet(conn, year, month)
    if sheet is None:
        raise AppError("这个月还没有汇款表", status_code=404, code="NOT_FOUND")
    day_count = as_int(sheet["dayCount"])
    rows = sheet["rows"]
    if not isinstance(rows, list):
        raise AppError("汇款月表数据异常")

    workbook = Workbook()
    ws = workbook.active
    ws.title = "汇款月表"
    _prev_year, prev_month = previous_year_month(year, month)
    # 与原 Excel 一致：1 月表头写「12月余额」，不带年份。
    opening_label = f"{prev_month}月余额"

    ws.cell(1, 1, "门店编号及名称")
    ws.cell(1, 2, opening_label)
    for day in range(1, day_count + 1):
        col = 2 + (day - 1) * 2 + 1
        ws.cell(1, col, f"{month}月{day}日")
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 1)
        ws.cell(2, col, "汇款")
        ws.cell(2, col + 1, "发货")
    remit_total_col = 3 + day_count * 2
    ship_total_col = remit_total_col + 1
    balance_col = ship_total_col + 1
    ws.cell(1, remit_total_col, "汇款总额")
    ws.cell(1, ship_total_col, "发货总额")
    ws.cell(1, balance_col, "汇款-发货=余额")

    header_font = Font(bold=True)
    for col in range(1, balance_col + 1):
        cell = ws.cell(1, col)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if col >= 3:
            ws.cell(2, col).alignment = Alignment(horizontal="center")

    for index, row in enumerate(rows, start=3):
        if not isinstance(row, dict):
            continue
        ws.cell(index, 1, as_str(row["displayName"]))
        ws.cell(index, 2, _decimal_or_none(row["openingBalance"]))
        cells = row["cells"]
        if not isinstance(cells, dict):
            cells = {}
        for day in range(1, day_count + 1):
            day_cell = cells.get(str(day))
            remit_col = 2 + (day - 1) * 2 + 1
            ship_col = remit_col + 1
            if isinstance(day_cell, dict):
                remit = day_cell.get("remit")
                ship = day_cell.get("ship")
                if isinstance(remit, str):
                    ws.cell(index, remit_col, _decimal_or_none(remit))
                if isinstance(ship, str):
                    ws.cell(index, ship_col, _decimal_or_none(ship))
        ws.cell(index, remit_total_col, _decimal_or_none(row["remitTotal"]))
        ws.cell(index, ship_total_col, _decimal_or_none(row["shipTotal"]))
        ws.cell(index, balance_col, _decimal_or_none(row["balance"]))

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 12
    for col in range(3, balance_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 10
    ws.freeze_panes = "C3"

    buffer = BytesIO()
    workbook.save(buffer)
    filename = f"汇款月表-{year}年{month}月.xlsx"
    return buffer.getvalue(), filename


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        return None
    return Decimal(value)
