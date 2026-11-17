from pathlib import Path

from psycopg import Connection

from app.importer.models import ParsedLine, ParsedRemittance, ParsedShipment


def get_or_create_store(
    conn: Connection,
    raw_name: str,
    source: str,
    phone: str | None = None,
    address: str | None = None,
) -> tuple[int, bool]:
    existing = conn.execute(
        """
        SELECT store_id
        FROM store_aliases
        WHERE raw_name = %s AND source = %s
        """,
        (raw_name, source),
    ).fetchone()
    if existing is not None:
        store_id = _int_id(existing["store_id"])
        if phone is not None or address is not None:
            conn.execute(
                """
                UPDATE stores
                SET phone = COALESCE(phone, %s),
                    address = COALESCE(address, %s),
                    updated_at = now()
                WHERE id = %s
                """,
                (phone, address, store_id),
            )
        return store_id, False
    inserted = conn.execute(
        """
        INSERT INTO stores (display_name, phone, address)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (raw_name, phone, address),
    ).fetchone()
    if inserted is None:
        raise RuntimeError("创建门店失败")
    store_id = _int_id(inserted["id"])
    conn.execute(
        """
        INSERT INTO store_aliases (store_id, raw_name, source)
        VALUES (%s, %s, %s)
        """,
        (store_id, raw_name, source),
    )
    return store_id, True


def replace_source_file(conn: Connection, relative_path: str, mode: str) -> str:
    existing = conn.execute(
        "SELECT id FROM source_files WHERE relative_path = %s",
        (relative_path,),
    ).fetchone()
    if existing is None:
        return "import"
    if mode == "skip":
        return "skip"
    conn.execute("DELETE FROM source_files WHERE id = %s", (_int_id(existing["id"]),))
    return "import"


def insert_source_file(
    conn: Connection,
    kind: str,
    relative_path: str,
    file_name: str,
    year: int,
    month: int,
    batch_no: int,
    batch_label: str,
    biz_date: object,
    sheet_name: str,
) -> int:
    inserted = conn.execute(
        """
        INSERT INTO source_files (
            kind, relative_path, file_name, year, month, batch_no, batch_label, biz_date, sheet_name
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (kind, relative_path, file_name, year, month, batch_no, batch_label, biz_date, sheet_name),
    ).fetchone()
    if inserted is None:
        raise RuntimeError("写入源文件失败")
    return _int_id(inserted["id"])


def insert_warnings(conn: Connection, source_file_id: int, warnings: list) -> None:
    if not warnings:
        return
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO import_warnings (source_file_id, code, message)
            VALUES (%s, %s, %s)
            """,
            [(source_file_id, item.code, item.message) for item in warnings],
        )


def persist_remittance(
    conn: Connection,
    relative_path: str,
    file_name: str,
    year: int,
    month: int,
    parsed: ParsedRemittance,
    mode: str,
) -> tuple[str, int]:
    action = replace_source_file(conn, relative_path, mode)
    if action == "skip":
        return "skipped", 0
    source_file_id = insert_source_file(
        conn, "remittance", relative_path, file_name, year, month, 0, "", None, parsed.sheet_name
    )
    sheet = conn.execute(
        """
        INSERT INTO remittance_sheets (source_file_id, year, month, day_count)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (source_file_id, year, month, parsed.day_count),
    ).fetchone()
    if sheet is None:
        raise RuntimeError("写入汇款月表失败")
    sheet_id = _int_id(sheet["id"])
    created = 0
    for row in parsed.rows:
        store_id, is_new = get_or_create_store(conn, row.raw_name, "remittance")
        if is_new:
            created += 1
        inserted = conn.execute(
            """
            INSERT INTO remittance_rows (
                sheet_id, store_id, row_index, imported_raw_name, opening_balance
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (sheet_id, store_id, row.row_index, row.raw_name, row.opening_balance),
        ).fetchone()
        if inserted is None:
            raise RuntimeError("写入汇款行失败")
        row_id = _int_id(inserted["id"])
        if row.cells:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO remittance_cells (row_id, day, kind, amount)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [(row_id, cell.day, cell.kind, cell.amount) for cell in row.cells],
                )
    insert_warnings(conn, source_file_id, parsed.warnings)
    return "imported", created


def persist_shipment(
    conn: Connection,
    relative_path: str,
    location_year: int,
    location_month: int,
    location_batch: int,
    location_batch_label: str,
    location_biz_date: object,
    file_name: str,
    parsed: ParsedShipment,
    mode: str,
) -> tuple[str, int, int, int]:
    action = replace_source_file(conn, relative_path, mode)
    if action == "skip":
        return "skipped", 0, 0, 0
    source_file_id = insert_source_file(
        conn,
        "shipment",
        relative_path,
        file_name,
        location_year,
        location_month,
        location_batch,
        location_batch_label,
        location_biz_date,
        parsed.sheet_name,
    )
    created = 0
    line_count = 0
    for order_index, order in enumerate(parsed.orders, start=1):
        store_id, is_new = get_or_create_store(
            conn,
            order.customer_raw_name,
            "shipment",
            order.phone,
            order.address,
        )
        if is_new:
            created += 1
        inserted = conn.execute(
            """
            INSERT INTO shipment_orders (
                source_file_id, store_id, order_index, biz_date, customer_raw_name,
                market_name, phone, address, price_ratio, ship_date_text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                source_file_id,
                store_id,
                order_index,
                location_biz_date,
                order.customer_raw_name,
                order.market_name,
                order.phone,
                order.address,
                order.price_ratio,
                order.ship_date_text,
            ),
        ).fetchone()
        if inserted is None:
            raise RuntimeError("写入发货单失败")
        order_id = _int_id(inserted["id"])
        if order.lines:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO shipment_lines (
                        order_id, line_index, product_name, unit, order_qty, ship_qty,
                        gift_qty, weight_total, actual_weight, gift_weight, actual_qty,
                        unit_price, amount
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [_line_params(order_id, line_index, line) for line_index, line in enumerate(order.lines, start=1)],
                )
            line_count += len(order.lines)
    if parsed.conflicts:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO date_conflicts (source_file_id, cell_text, parsed_cell_date, biz_date)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (source_file_id, item.cell_text, item.parsed_cell_date, item.biz_date)
                    for item in parsed.conflicts
                ],
            )
    insert_warnings(conn, source_file_id, parsed.warnings)
    return "imported", created, len(parsed.orders), line_count


def _line_params(order_id: int, line_index: int, line: ParsedLine) -> tuple[object, ...]:
    return (
        order_id,
        line_index,
        line.product_name,
        line.unit,
        line.order_qty,
        line.ship_qty,
        line.gift_qty,
        line.weight_total,
        line.actual_weight,
        line.gift_weight,
        line.actual_qty,
        line.unit_price,
        line.amount,
    )


def _int_id(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("主键类型不对")


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
