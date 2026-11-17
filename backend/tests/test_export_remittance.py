from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook
from psycopg import Connection

from app.services.export_remittance import export_remittance_xlsx


def test_export_remittance_month_workbook(conn: Connection) -> None:
    store = conn.execute(
        "INSERT INTO stores (display_name) VALUES ('021东大里-李大进') RETURNING id"
    ).fetchone()
    assert store is not None
    store_id = int(store["id"])
    sheet = conn.execute(
        """
        INSERT INTO remittance_sheets (year, month, day_count)
        VALUES (2026, 1, 31)
        RETURNING id
        """
    ).fetchone()
    assert sheet is not None
    row = conn.execute(
        """
        INSERT INTO remittance_rows (
            sheet_id, store_id, row_index, imported_raw_name, opening_balance
        ) VALUES (%s, %s, 1, '021东大里-李大进', -5514.27)
        RETURNING id
        """,
        (sheet["id"], store_id),
    ).fetchone()
    assert row is not None
    conn.execute(
        """
        INSERT INTO remittance_cells (row_id, day, kind, amount)
        VALUES (%s, 1, 'ship', 633.00), (%s, 2, 'remit', 1000.00)
        """,
        (row["id"], row["id"]),
    )

    content, filename = export_remittance_xlsx(conn, 2026, 1)
    assert filename == "汇款月表-2026年1月.xlsx"
    book = load_workbook(BytesIO(content))
    ws = book.active
    assert ws is not None
    assert ws.cell(1, 1).value == "门店编号及名称"
    assert ws.cell(1, 2).value == "12月余额"
    assert ws.cell(1, 3).value == "1月1日"
    assert ws.cell(2, 3).value == "汇款"
    assert ws.cell(2, 4).value == "发货"
    assert ws.cell(3, 1).value == "021东大里-李大进"
    assert _num(ws.cell(3, 2).value) == Decimal("-5514.27")
    assert _num(ws.cell(3, 4).value) == Decimal("633.00")
    assert _num(ws.cell(3, 5).value) == Decimal("1000.00")
    assert _num(ws.cell(3, 65).value) == Decimal("1000.00")
    assert _num(ws.cell(3, 66).value) == Decimal("633.00")
    assert _num(ws.cell(3, 67).value) == Decimal("-5147.27")


def _num(value: object) -> Decimal:
    assert value is not None
    return Decimal(str(value))
