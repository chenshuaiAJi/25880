from decimal import Decimal

from psycopg import Connection

from app.domain.balance import month_balance
from app.domain.money import money_text
from app.errors import AppError
from app.readers.stores import get_store
from app.readers.values import as_decimal, as_int, as_str
from app.services.remittances import merge_remittance_rows
from app.services.shipments import _ensure_store


def update_store_profile(
    conn: Connection,
    store_id: int,
    *,
    display_name: str | None,
    code: str | None,
    manager_name: str | None,
    phone: str | None,
    address: str | None,
) -> dict[str, object]:
    _ensure_store(conn, store_id)
    current = get_store(conn, store_id)
    if current is None:
        raise AppError("找不到这家门店", status_code=404, code="NOT_FOUND")
    next_name = display_name if display_name is not None else as_str(current["displayName"])
    cleaned = next_name.strip()
    if cleaned == "":
        raise AppError("显示名不能为空")
    conn.execute(
        """
        UPDATE stores
        SET display_name = %s,
            code = %s,
            manager_name = %s,
            phone = %s,
            address = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (
            cleaned,
            _blank_to_none(code if code is not None else current["code"]),
            _blank_to_none(manager_name if manager_name is not None else current["managerName"]),
            _blank_to_none(phone if phone is not None else current["phone"]),
            _blank_to_none(address if address is not None else current["address"]),
            store_id,
        ),
    )
    updated = get_store(conn, store_id)
    if updated is None:
        raise AppError("找不到这家门店", status_code=404, code="NOT_FOUND")
    return updated


def preview_merge_stores(conn: Connection, keep_store_id: int, merge_store_id: int) -> dict[str, object]:
    if keep_store_id == merge_store_id:
        raise AppError("不能把门店合并到自己")
    keep = get_store(conn, keep_store_id)
    merge = get_store(conn, merge_store_id)
    if keep is None or merge is None:
        raise AppError("找不到要合并的门店", status_code=404, code="NOT_FOUND")
    overlaps = _overlap_days(conn, keep_store_id, merge_store_id)
    order_row = conn.execute(
        "SELECT COUNT(*) AS total FROM shipment_orders WHERE store_id = %s",
        (merge_store_id,),
    ).fetchone()
    remittance_row = conn.execute(
        "SELECT COUNT(*) AS total FROM remittance_rows WHERE store_id = %s",
        (merge_store_id,),
    ).fetchone()
    if order_row is None or remittance_row is None:
        raise AppError("统计合并单据失败")
    return {
        "keepStore": keep,
        "mergeStore": merge,
        "orderCount": as_int(order_row["total"]),
        "remittanceRowCount": as_int(remittance_row["total"]),
        "overlaps": overlaps,
    }


def merge_stores(
    conn: Connection,
    keep_store_id: int,
    merge_store_id: int,
    display_name: str | None,
) -> dict[str, object]:
    preview = preview_merge_stores(conn, keep_store_id, merge_store_id)
    if display_name is not None and display_name.strip() != "":
        conn.execute(
            "UPDATE stores SET display_name = %s, updated_at = now() WHERE id = %s",
            (display_name.strip(), keep_store_id),
        )
    # 先迁别名，再迁单据，再合并同月汇款行。
    aliases = conn.execute(
        """
        SELECT id, raw_name, source
        FROM store_aliases
        WHERE store_id = %s
        """,
        (merge_store_id,),
    ).fetchall()
    for alias in aliases:
        conflict = conn.execute(
            """
            SELECT id
            FROM store_aliases
            WHERE raw_name = %s AND source = %s AND store_id = %s
            """,
            (as_str(alias["raw_name"]), as_str(alias["source"]), keep_store_id),
        ).fetchone()
        if conflict is None:
            conn.execute(
                "UPDATE store_aliases SET store_id = %s WHERE id = %s",
                (keep_store_id, as_int(alias["id"])),
            )
        else:
            conn.execute("DELETE FROM store_aliases WHERE id = %s", (as_int(alias["id"]),))

    conn.execute(
        "UPDATE shipment_orders SET store_id = %s WHERE store_id = %s",
        (keep_store_id, merge_store_id),
    )

    pairs = conn.execute(
        """
        SELECT keep_row.id AS keep_id, merge_row.id AS merge_id
        FROM remittance_rows merge_row
        JOIN remittance_rows keep_row
          ON keep_row.sheet_id = merge_row.sheet_id
         AND keep_row.store_id = %s
        WHERE merge_row.store_id = %s
        """,
        (keep_store_id, merge_store_id),
    ).fetchall()
    for pair in pairs:
        merge_remittance_rows(conn, keep_row_id=as_int(pair["keep_id"]), drop_row_id=as_int(pair["merge_id"]))

    conn.execute(
        "UPDATE remittance_rows SET store_id = %s WHERE store_id = %s",
        (keep_store_id, merge_store_id),
    )
    conn.execute("DELETE FROM stores WHERE id = %s", (merge_store_id,))
    result = get_store(conn, keep_store_id)
    if result is None:
        raise AppError("合并后门店丢失")
    result["mergePreview"] = preview
    return result


def _overlap_days(conn: Connection, keep_store_id: int, merge_store_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            s.year,
            s.month,
            keep_row.id AS keep_row_id,
            merge_row.id AS merge_row_id,
            keep_row.opening_balance AS keep_opening,
            merge_row.opening_balance AS merge_opening
        FROM remittance_rows keep_row
        JOIN remittance_rows merge_row
          ON merge_row.sheet_id = keep_row.sheet_id
        JOIN remittance_sheets s ON s.id = keep_row.sheet_id
        WHERE keep_row.store_id = %s AND merge_row.store_id = %s
        ORDER BY s.year, s.month
        """,
        (keep_store_id, merge_store_id),
    ).fetchall()
    overlaps: list[dict[str, object]] = []
    for row in rows:
        keep_cells = _cell_map(conn, as_int(row["keep_row_id"]))
        merge_cells = _cell_map(conn, as_int(row["merge_row_id"]))
        days = sorted(set(keep_cells) | set(merge_cells))
        day_items: list[dict[str, object]] = []
        for day, kind in days:
            left = keep_cells.get((day, kind), Decimal("0"))
            right = merge_cells.get((day, kind), Decimal("0"))
            if left == 0 and right == 0:
                continue
            if (day, kind) in keep_cells and (day, kind) in merge_cells:
                day_items.append(
                    {
                        "day": day,
                        "kind": kind,
                        "keepAmount": money_text(left),
                        "mergeAmount": money_text(right),
                        "sumAmount": money_text(left + right),
                    }
                )
        keep_opening = as_decimal(row["keep_opening"])
        merge_opening = as_decimal(row["merge_opening"])
        overlaps.append(
            {
                "year": as_int(row["year"]),
                "month": as_int(row["month"]),
                "keepOpening": money_text(keep_opening),
                "mergeOpening": money_text(merge_opening),
                "sumOpening": money_text(keep_opening + merge_opening),
                "days": day_items,
            }
        )
    return overlaps


def _cell_map(conn: Connection, row_id: int) -> dict[tuple[int, str], Decimal]:
    cells = conn.execute(
        """
        SELECT day, kind, amount
        FROM remittance_cells
        WHERE row_id = %s
        """,
        (row_id,),
    ).fetchall()
    return {(as_int(cell["day"]), as_str(cell["kind"])): as_decimal(cell["amount"]) for cell in cells}


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def store_balance_for_sheet(conn: Connection, store_id: int, year: int, month: int) -> Decimal | None:
    row = conn.execute(
        """
        SELECT
            r.opening_balance,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'remit'), 0) AS remit_total,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'ship'), 0) AS ship_total
        FROM remittance_rows r
        JOIN remittance_sheets s ON s.id = r.sheet_id
        LEFT JOIN remittance_cells c ON c.row_id = r.id
        WHERE r.store_id = %s AND s.year = %s AND s.month = %s
        GROUP BY r.id
        """,
        (store_id, year, month),
    ).fetchone()
    if row is None:
        return None
    return month_balance(
        as_decimal(row["opening_balance"]),
        as_decimal(row["remit_total"]),
        as_decimal(row["ship_total"]),
    )
