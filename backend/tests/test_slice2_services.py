from datetime import date
from decimal import Decimal

import pytest
from psycopg import Connection

from app.domain.money import money_text
from app.errors import AppError
from app.services.next_month import create_next_month, list_opening_mismatches, preview_create_next_month
from app.services.remittances import add_remittance_row, update_remittance_cell, update_remittance_opening
from app.services.shipments import reassign_shipment_order, update_shipment_line
from app.services.stores import merge_stores, preview_merge_stores, update_store_profile


def _seed_store(conn: Connection, name: str) -> int:
    store = conn.execute(
        "INSERT INTO stores (display_name) VALUES (%s) RETURNING id",
        (name,),
    ).fetchone()
    assert store is not None
    store_id = int(store["id"])
    conn.execute(
        "INSERT INTO store_aliases (store_id, raw_name, source) VALUES (%s, %s, 'remittance')",
        (store_id, name),
    )
    return store_id


def _seed_sheet(conn: Connection, year: int, month: int, day_count: int = 31) -> int:
    sheet = conn.execute(
        """
        INSERT INTO remittance_sheets (year, month, day_count)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (year, month, day_count),
    ).fetchone()
    assert sheet is not None
    return int(sheet["id"])


def _seed_row(conn: Connection, sheet_id: int, store_id: int, name: str, opening: str, row_index: int = 1) -> int:
    row = conn.execute(
        """
        INSERT INTO remittance_rows (sheet_id, store_id, row_index, imported_raw_name, opening_balance)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (sheet_id, store_id, row_index, name, Decimal(opening)),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def test_remittance_cell_edit_recalculates_balance(conn: Connection) -> None:
    store_id = _seed_store(conn, "021东大里-李大进")
    sheet_id = _seed_sheet(conn, 2026, 1)
    row_id = _seed_row(conn, sheet_id, store_id, "021东大里-李大进", "-5514.27")
    sheet = update_remittance_cell(conn, row_id, 1, "remit", "1000.00")
    row = sheet["rows"][0]
    assert isinstance(row, dict)
    assert row["remitTotal"] == "1000.00"
    assert row["balance"] == money_text(Decimal("-5514.27") + Decimal("1000.00"))
    sheet = update_remittance_opening(conn, row_id, "-5000.00")
    row = sheet["rows"][0]
    assert isinstance(row, dict)
    assert row["openingBalance"] == "-5000.00"
    assert row["balance"] == "-4000.00"


def test_add_remittance_row_existing_and_new(conn: Connection) -> None:
    existing = _seed_store(conn, "已有店")
    other = _seed_store(conn, "未进本月店")
    jan = _seed_sheet(conn, 2026, 1)
    _seed_row(conn, jan, existing, "已有店", "100.00")
    jan_other = _seed_row(conn, jan, other, "未进本月店", "20.00", row_index=2)
    update_remittance_cell(conn, jan_other, 1, "remit", "30.00")
    feb = _seed_sheet(conn, 2026, 2, day_count=28)
    _seed_row(conn, feb, existing, "已有店", "100.00")

    sheet = add_remittance_row(conn, 2026, 2, store_id=other)
    added = next(row for row in sheet["rows"] if row["storeId"] == other)  # type: ignore[index]
    assert added["openingBalance"] == "50.00"

    with pytest.raises(AppError, match="已经在本月"):
        add_remittance_row(conn, 2026, 2, store_id=other)

    created = add_remittance_row(conn, 2026, 2, display_name="临时加货店", opening_balance="12.50")
    assert any(
        row["displayName"] == "临时加货店" and row["openingBalance"] == "12.50"
        for row in created["rows"]  # type: ignore[index]
    )


def test_shipment_line_edit_and_reassign(conn: Connection) -> None:
    keep = _seed_store(conn, "李大进-东大里店")
    other = _seed_store(conn, "临时店")
    conn.execute(
        "INSERT INTO store_aliases (store_id, raw_name, source) VALUES (%s, %s, 'shipment')",
        (keep, "李大进-东大里店"),
    )
    source = conn.execute(
        """
        INSERT INTO source_files (
            kind, relative_path, file_name, year, month, batch_no, batch_label, biz_date, sheet_name
        ) VALUES ('shipment', 'a.xls', 'a.xls', 2026, 1, 0, '', '2026-01-01', 'Sheet1')
        RETURNING id
        """
    ).fetchone()
    assert source is not None
    order = conn.execute(
        """
        INSERT INTO shipment_orders (
            source_file_id, store_id, order_index, biz_date, customer_raw_name
        ) VALUES (%s, %s, 1, '2026-01-01', '李大进-东大里店')
        RETURNING id
        """,
        (source["id"], keep),
    ).fetchone()
    assert order is not None
    order_id = int(order["id"])
    conn.execute(
        """
        INSERT INTO shipment_lines (
            order_id, line_index, product_name, ship_qty, unit_price, amount
        ) VALUES (%s, 1, '去皮大五花肉15kg/件', 30, 21.2, 636)
        """,
        (order_id,),
    )
    updated = update_shipment_line(
        conn,
        order_id,
        1,
        ship_qty=None,
        unit_price="22",
        amount=None,
        edited="price",
    )
    assert updated["totalAmount"] == "660.00"
    assert updated["lines"][0]["amount"] == "660.00"  # type: ignore[index]

    moved = reassign_shipment_order(conn, order_id, other, "one")
    assert moved["storeId"] == other
    same = conn.execute(
        "SELECT COUNT(*) AS total FROM shipment_orders WHERE store_id = %s",
        (keep,),
    ).fetchone()
    assert same is not None
    assert int(same["total"]) == 0


def test_merge_stores_adds_same_day_amounts(conn: Connection) -> None:
    keep = _seed_store(conn, "017欢墩店-胡尊柳")
    merge = _seed_store(conn, "顾延红-欢墩店")
    conn.execute(
        "INSERT INTO store_aliases (store_id, raw_name, source) VALUES (%s, %s, 'shipment')",
        (merge, "顾延红-欢墩店"),
    )
    sheet_id = _seed_sheet(conn, 2026, 1)
    keep_row = _seed_row(conn, sheet_id, keep, "017欢墩店-胡尊柳", "-365.00", 1)
    merge_row = _seed_row(conn, sheet_id, merge, "顾延红-欢墩店", "10.00", 2)
    conn.execute(
        "INSERT INTO remittance_cells (row_id, day, kind, amount) VALUES (%s, 1, 'ship', 100)",
        (keep_row,),
    )
    conn.execute(
        "INSERT INTO remittance_cells (row_id, day, kind, amount) VALUES (%s, 1, 'ship', 50)",
        (merge_row,),
    )
    preview = preview_merge_stores(conn, keep, merge)
    assert preview["overlaps"][0]["days"][0]["sumAmount"] == "150.00"  # type: ignore[index]
    result = merge_stores(conn, keep, merge, "欢墩店")
    assert result["displayName"] == "欢墩店"
    assert result["orderCount"] == 0
    cell = conn.execute(
        """
        SELECT amount
        FROM remittance_cells c
        JOIN remittance_rows r ON r.id = c.row_id
        WHERE r.store_id = %s AND c.day = 1 AND c.kind = 'ship'
        """,
        (keep,),
    ).fetchone()
    assert cell is not None
    assert cell["amount"] == Decimal("150.00")
    aliases = conn.execute(
        "SELECT raw_name FROM store_aliases WHERE store_id = %s ORDER BY raw_name",
        (keep,),
    ).fetchall()
    names = [row["raw_name"] for row in aliases]
    assert "顾延红-欢墩店" in names
    assert conn.execute("SELECT 1 FROM stores WHERE id = %s", (merge,)).fetchone() is None


def test_create_next_month_rules(conn: Connection) -> None:
    store_id = _seed_store(conn, "沙河-张振习-33")
    sheet_id = _seed_sheet(conn, 2026, 10, day_count=31)
    row_id = _seed_row(conn, sheet_id, store_id, "沙河-张振习-33", "100.00")
    conn.execute(
        "INSERT INTO remittance_cells (row_id, day, kind, amount) VALUES (%s, 1, 'remit', 20)",
        (row_id,),
    )
    blocked = preview_create_next_month(conn, 2026, 10, today=date(2026, 10, 15))
    assert blocked["canCreate"] is False
    assert any("还没结束" in item for item in blocked["blockers"])  # type: ignore[union-attr]

    preview = preview_create_next_month(conn, 2026, 10, today=date(2026, 10, 31))
    assert preview["canCreate"] is True
    assert preview["targetYear"] == 2026
    assert preview["targetMonth"] == 11
    assert preview["targetDayCount"] == 30
    assert preview["stores"][0]["openingBalance"] == "120.00"  # type: ignore[index]

    created = create_next_month(conn, 2026, 10, today=date(2026, 10, 31))
    sheet = created["sheet"]
    assert isinstance(sheet, dict)
    assert sheet["year"] == 2026
    assert sheet["month"] == 11
    assert sheet["dayCount"] == 30
    assert sheet["rows"][0]["openingBalance"] == "120.00"  # type: ignore[index]
    assert sheet["rows"][0]["cells"] == {}  # type: ignore[index]

    again = preview_create_next_month(conn, 2026, 10, today=date(2026, 10, 31))
    assert again["canCreate"] is False
    assert any("已经存在" in item for item in again["blockers"])  # type: ignore[union-attr]


def test_create_december_to_next_year(conn: Connection) -> None:
    store_id = _seed_store(conn, "徐屯")
    sheet_id = _seed_sheet(conn, 2026, 12, day_count=31)
    _seed_row(conn, sheet_id, store_id, "徐屯", "8.00")
    created = create_next_month(conn, 2026, 12, today=date(2026, 12, 31))
    sheet = created["sheet"]
    assert isinstance(sheet, dict)
    assert sheet["year"] == 2027
    assert sheet["month"] == 1
    assert sheet["dayCount"] == 31


def test_opening_mismatch_and_apply(conn: Connection) -> None:
    store_id = _seed_store(conn, "夹山专柜-李静")
    oct_sheet = _seed_sheet(conn, 2026, 10)
    nov_sheet = _seed_sheet(conn, 2026, 11)
    oct_row = _seed_row(conn, oct_sheet, store_id, "夹山专柜-李静", "10.00")
    conn.execute(
        "INSERT INTO remittance_cells (row_id, day, kind, amount) VALUES (%s, 1, 'remit', 5)",
        (oct_row,),
    )
    _seed_row(conn, nov_sheet, store_id, "夹山专柜-李静", "10.00")
    gaps = list_opening_mismatches(conn, 2026, 11)
    assert len(gaps) == 1
    assert gaps[0]["previousBalance"] == "15.00"
    assert gaps[0]["currentOpening"] == "10.00"
    from app.services.next_month import apply_opening_from_previous

    applied = apply_opening_from_previous(conn, 2026, 11, None)
    assert applied["updated"] == 1
    assert applied["remaining"] == []


def test_display_name_change(conn: Connection) -> None:
    store_id = _seed_store(conn, "旧名")
    updated = update_store_profile(
        conn,
        store_id,
        display_name="新显示名",
        code="021",
        manager_name="张三",
        phone="13800000000",
        address="赣榆",
    )
    assert updated["displayName"] == "新显示名"
    assert updated["code"] == "021"
    assert updated["managerName"] == "张三"


def test_zero_qty_amount_edit_rejected(conn: Connection) -> None:
    store_id = _seed_store(conn, "测试店")
    source = conn.execute(
        """
        INSERT INTO source_files (
            kind, relative_path, file_name, year, month, batch_no, batch_label, biz_date, sheet_name
        ) VALUES ('shipment', 'b.xls', 'b.xls', 2026, 1, 0, '', '2026-01-02', 'Sheet1')
        RETURNING id
        """
    ).fetchone()
    assert source is not None
    order = conn.execute(
        """
        INSERT INTO shipment_orders (
            source_file_id, store_id, order_index, biz_date, customer_raw_name
        ) VALUES (%s, %s, 1, '2026-01-02', '测试店')
        RETURNING id
        """,
        (source["id"], store_id),
    ).fetchone()
    assert order is not None
    conn.execute(
        """
        INSERT INTO shipment_lines (
            order_id, line_index, product_name, ship_qty, unit_price, amount
        ) VALUES (%s, 1, '测试品', 0, 10, 0)
        """,
        (order["id"],),
    )
    with pytest.raises(AppError, match="数量为 0"):
        update_shipment_line(
            conn,
            int(order["id"]),
            1,
            ship_qty=None,
            unit_price=None,
            amount="100",
            edited="amount",
        )
