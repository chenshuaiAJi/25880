from decimal import Decimal

from psycopg import Connection

from app.domain.balance import month_balance, sum_money
from app.domain.line_amount import parse_money_input
from app.domain.money import money_text
from app.domain.month_nav import previous_year_month
from app.errors import AppError
from app.importer.persist import get_or_create_store
from app.readers.remittances import get_remittance_sheet
from app.readers.values import as_decimal, as_int, as_str
from app.services.shipments import _ensure_store, _move_alias


def add_remittance_row(
    conn: Connection,
    year: int,
    month: int,
    *,
    store_id: int | None = None,
    display_name: str | None = None,
    opening_balance: str | None = None,
) -> dict[str, object]:
    """在当月汇款表追加一门店行。可挂已有门店，或按名称新建门店。"""
    sheet_meta = conn.execute(
        """
        SELECT id, year, month
        FROM remittance_sheets
        WHERE year = %s AND month = %s
        """,
        (year, month),
    ).fetchone()
    if sheet_meta is None:
        raise AppError("这个月还没有汇款表", status_code=404, code="NOT_FOUND")
    sheet_id = as_int(sheet_meta["id"])

    cleaned_name = display_name.strip() if isinstance(display_name, str) else ""
    if store_id is not None:
        _ensure_store(conn, store_id)
        resolved_store_id = store_id
        store_row = conn.execute(
            "SELECT display_name FROM stores WHERE id = %s",
            (resolved_store_id,),
        ).fetchone()
        if store_row is None:
            raise AppError("找不到门店", status_code=404, code="NOT_FOUND")
        raw_name = as_str(store_row["display_name"])
    elif cleaned_name:
        resolved_store_id, _ = get_or_create_store(conn, cleaned_name, "remittance")
        raw_name = cleaned_name
    else:
        raise AppError("请选择已有门店，或填写新门店名称")

    duplicate = conn.execute(
        """
        SELECT id
        FROM remittance_rows
        WHERE sheet_id = %s AND store_id = %s
        """,
        (sheet_id, resolved_store_id),
    ).fetchone()
    if duplicate is not None:
        raise AppError("这家店已经在本月汇款表里")

    if opening_balance is None or (isinstance(opening_balance, str) and opening_balance.strip() == ""):
        opening = _previous_month_balance(conn, year, month, resolved_store_id)
        if opening is None:
            opening = Decimal("0")
    else:
        parsed = parse_money_input(opening_balance, allow_empty=False)
        if parsed is None:
            raise AppError("上月余额格式不正确")
        opening = parsed

    next_index_row = conn.execute(
        """
        SELECT COALESCE(MAX(row_index), 0) + 1 AS next_index
        FROM remittance_rows
        WHERE sheet_id = %s
        """,
        (sheet_id,),
    ).fetchone()
    if next_index_row is None:
        raise AppError("计算行号失败")
    row_index = as_int(next_index_row["next_index"])

    inserted = conn.execute(
        """
        INSERT INTO remittance_rows (
            sheet_id, store_id, row_index, imported_raw_name, opening_balance
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (sheet_id, resolved_store_id, row_index, raw_name, opening),
    ).fetchone()
    if inserted is None:
        raise AppError("增加门店行失败")
    sheet = get_remittance_sheet(conn, year, month)
    if sheet is None:
        raise AppError("找不到汇款月表", status_code=404, code="NOT_FOUND")
    return sheet


def _previous_month_balance(
    conn: Connection,
    year: int,
    month: int,
    store_id: int,
) -> Decimal | None:
    prev_year, prev_month = previous_year_month(year, month)
    row = conn.execute(
        """
        SELECT
            r.opening_balance,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'remit'), 0) AS remit_total,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'ship'), 0) AS ship_total
        FROM remittance_rows r
        JOIN remittance_sheets s ON s.id = r.sheet_id
        LEFT JOIN remittance_cells c ON c.row_id = r.id
        WHERE s.year = %s AND s.month = %s AND r.store_id = %s
        GROUP BY r.id
        """,
        (prev_year, prev_month, store_id),
    ).fetchone()
    if row is None:
        return None
    return month_balance(
        as_decimal(row["opening_balance"]),
        as_decimal(row["remit_total"]),
        as_decimal(row["ship_total"]),
    )


def update_remittance_opening(conn: Connection, row_id: int, opening_balance: str) -> dict[str, object]:
    row = _load_row(conn, row_id)
    amount = parse_money_input(opening_balance, allow_empty=False)
    if amount is None:
        raise AppError("上月余额不能为空")
    conn.execute(
        "UPDATE remittance_rows SET opening_balance = %s WHERE id = %s",
        (amount, row_id),
    )
    return _sheet_for_row(conn, row)


def update_remittance_cell(
    conn: Connection,
    row_id: int,
    day: int,
    kind: str,
    amount: str | None,
) -> dict[str, object]:
    if kind not in {"remit", "ship"}:
        raise AppError("单元格类型只能是汇款或发货")
    row = _load_row(conn, row_id)
    day_count = as_int(row["day_count"])
    if day < 1 or day > day_count:
        raise AppError("日期超出本月列数")
    parsed = parse_money_input(amount, allow_empty=True)
    existing = conn.execute(
        """
        SELECT id
        FROM remittance_cells
        WHERE row_id = %s AND day = %s AND kind = %s
        """,
        (row_id, day, kind),
    ).fetchone()
    if parsed is None:
        if existing is not None:
            conn.execute("DELETE FROM remittance_cells WHERE id = %s", (as_int(existing["id"]),))
    elif existing is None:
        conn.execute(
            """
            INSERT INTO remittance_cells (row_id, day, kind, amount)
            VALUES (%s, %s, %s, %s)
            """,
            (row_id, day, kind, parsed),
        )
    else:
        conn.execute(
            "UPDATE remittance_cells SET amount = %s WHERE id = %s",
            (parsed, as_int(existing["id"])),
        )
    return _sheet_for_row(conn, row)


def reassign_remittance_row(
    conn: Connection,
    row_id: int,
    target_store_id: int,
    mode: str,
) -> dict[str, object]:
    if mode not in {"one", "all"}:
        raise AppError("同步范围只能是只改这一行或同步全部")
    row = _load_row(conn, row_id)
    _ensure_store(conn, target_store_id)
    raw_name = as_str(row["imported_raw_name"])
    source_store_id = as_int(row["store_id"])
    if mode == "one":
        _attach_row_to_store(conn, row_id, as_int(row["sheet_id"]), target_store_id)
    else:
        matches = conn.execute(
            """
            SELECT id, sheet_id
            FROM remittance_rows
            WHERE imported_raw_name = %s AND store_id = %s
            """,
            (raw_name, source_store_id),
        ).fetchall()
        for item in matches:
            _attach_row_to_store(conn, as_int(item["id"]), as_int(item["sheet_id"]), target_store_id)
        _move_alias(conn, source_store_id, target_store_id, raw_name, "remittance")
    return _sheet_for_row(conn, row)


def row_totals(conn: Connection, row_id: int, opening: Decimal) -> dict[str, str]:
    cells = conn.execute(
        """
        SELECT kind, amount
        FROM remittance_cells
        WHERE row_id = %s
        """,
        (row_id,),
    ).fetchall()
    remit_total = sum_money([as_decimal(cell["amount"]) for cell in cells if as_str(cell["kind"]) == "remit"])
    ship_total = sum_money([as_decimal(cell["amount"]) for cell in cells if as_str(cell["kind"]) == "ship"])
    balance = month_balance(opening, remit_total, ship_total)
    return {
        "openingBalance": money_text(opening),
        "remitTotal": money_text(remit_total),
        "shipTotal": money_text(ship_total),
        "balance": money_text(balance),
    }


def _attach_row_to_store(conn: Connection, row_id: int, sheet_id: int, target_store_id: int) -> None:
    other = conn.execute(
        """
        SELECT id
        FROM remittance_rows
        WHERE sheet_id = %s AND store_id = %s AND id <> %s
        """,
        (sheet_id, target_store_id, row_id),
    ).fetchone()
    if other is None:
        conn.execute(
            "UPDATE remittance_rows SET store_id = %s WHERE id = %s",
            (target_store_id, row_id),
        )
        return
    # 同月目标店已有行：把金额并过去，再删当前行。
    merge_remittance_rows(conn, keep_row_id=as_int(other["id"]), drop_row_id=row_id)


def merge_remittance_rows(conn: Connection, keep_row_id: int, drop_row_id: int) -> None:
    keep = conn.execute(
        "SELECT id, opening_balance FROM remittance_rows WHERE id = %s",
        (keep_row_id,),
    ).fetchone()
    drop = conn.execute(
        "SELECT id, opening_balance FROM remittance_rows WHERE id = %s",
        (drop_row_id,),
    ).fetchone()
    if keep is None or drop is None:
        raise AppError("合并汇款行失败")
    opening = as_decimal(keep["opening_balance"]) + as_decimal(drop["opening_balance"])
    conn.execute(
        "UPDATE remittance_rows SET opening_balance = %s WHERE id = %s",
        (opening, keep_row_id),
    )
    drop_cells = conn.execute(
        """
        SELECT day, kind, amount
        FROM remittance_cells
        WHERE row_id = %s
        """,
        (drop_row_id,),
    ).fetchall()
    for cell in drop_cells:
        existing = conn.execute(
            """
            SELECT id, amount
            FROM remittance_cells
            WHERE row_id = %s AND day = %s AND kind = %s
            """,
            (keep_row_id, as_int(cell["day"]), as_str(cell["kind"])),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO remittance_cells (row_id, day, kind, amount)
                VALUES (%s, %s, %s, %s)
                """,
                (keep_row_id, as_int(cell["day"]), as_str(cell["kind"]), as_decimal(cell["amount"])),
            )
        else:
            conn.execute(
                "UPDATE remittance_cells SET amount = %s WHERE id = %s",
                (as_decimal(existing["amount"]) + as_decimal(cell["amount"]), as_int(existing["id"])),
            )
    conn.execute("DELETE FROM remittance_rows WHERE id = %s", (drop_row_id,))


def _load_row(conn: Connection, row_id: int) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            r.id,
            r.sheet_id,
            r.store_id,
            r.imported_raw_name,
            r.opening_balance,
            s.year,
            s.month,
            s.day_count
        FROM remittance_rows r
        JOIN remittance_sheets s ON s.id = r.sheet_id
        WHERE r.id = %s
        """,
        (row_id,),
    ).fetchone()
    if row is None:
        raise AppError("找不到这条汇款行", status_code=404, code="NOT_FOUND")
    return row


def _sheet_for_row(conn: Connection, row: dict[str, object]) -> dict[str, object]:
    sheet = get_remittance_sheet(conn, as_int(row["year"]), as_int(row["month"]))
    if sheet is None:
        raise AppError("找不到汇款月表", status_code=404, code="NOT_FOUND")
    return sheet
