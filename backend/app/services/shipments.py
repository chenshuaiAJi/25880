from psycopg import Connection

from app.domain.line_amount import EditedField, parse_money_input, parse_qty_input, recalculate_line
from app.errors import AppError
from app.readers.shipments import get_shipment
from app.readers.values import as_int, as_optional_decimal, as_str


def update_shipment_line(
    conn: Connection,
    order_id: int,
    line_index: int,
    *,
    ship_qty: str | None,
    unit_price: str | None,
    amount: str | None,
    edited: EditedField,
) -> dict[str, object]:
    line = conn.execute(
        """
        SELECT id, ship_qty, order_qty, unit_price, amount
        FROM shipment_lines
        WHERE order_id = %s AND line_index = %s
        """,
        (order_id, line_index),
    ).fetchone()
    if line is None:
        raise AppError("找不到这条商品明细", status_code=404, code="NOT_FOUND")

    current_qty = as_optional_decimal(line["ship_qty"])
    if current_qty is None:
        current_qty = as_optional_decimal(line["order_qty"])
    current_price = as_optional_decimal(line["unit_price"])
    current_amount = as_optional_decimal(line["amount"])

    next_qty = current_qty
    next_price = current_price
    next_amount = current_amount
    if edited == "qty":
        next_qty = parse_qty_input(ship_qty, allow_empty=False)
    elif edited == "price":
        next_price = parse_qty_input(unit_price, allow_empty=False)
    else:
        next_amount = parse_money_input(amount, allow_empty=False)

    qty, price, money = recalculate_line(next_qty, next_price, next_amount, edited)
    conn.execute(
        """
        UPDATE shipment_lines
        SET ship_qty = %s,
            unit_price = %s,
            amount = %s
        WHERE id = %s
        """,
        (qty, price, money, as_int(line["id"])),
    )
    order = get_shipment(conn, order_id)
    if order is None:
        raise AppError("找不到这张发货单", status_code=404, code="NOT_FOUND")
    return order


def reassign_shipment_order(
    conn: Connection,
    order_id: int,
    target_store_id: int,
    mode: str,
) -> dict[str, object]:
    if mode not in {"one", "all"}:
        raise AppError("同步范围只能是只改这一单或同步全部")
    order = conn.execute(
        """
        SELECT id, store_id, customer_raw_name
        FROM shipment_orders
        WHERE id = %s
        """,
        (order_id,),
    ).fetchone()
    if order is None:
        raise AppError("找不到这张发货单", status_code=404, code="NOT_FOUND")
    _ensure_store(conn, target_store_id)
    raw_name = as_str(order["customer_raw_name"])
    source_store_id = as_int(order["store_id"])
    if mode == "one":
        conn.execute(
            "UPDATE shipment_orders SET store_id = %s WHERE id = %s",
            (target_store_id, order_id),
        )
    else:
        conn.execute(
            """
            UPDATE shipment_orders
            SET store_id = %s
            WHERE customer_raw_name = %s AND store_id = %s
            """,
            (target_store_id, raw_name, source_store_id),
        )
        _move_alias(conn, source_store_id, target_store_id, raw_name, "shipment")
    result = get_shipment(conn, order_id)
    if result is None:
        raise AppError("找不到这张发货单", status_code=404, code="NOT_FOUND")
    return result


def _ensure_store(conn: Connection, store_id: int) -> None:
    exists = conn.execute("SELECT 1 FROM stores WHERE id = %s", (store_id,)).fetchone()
    if exists is None:
        raise AppError("找不到目标门店", status_code=404, code="NOT_FOUND")


def _move_alias(
    conn: Connection,
    source_store_id: int,
    target_store_id: int,
    raw_name: str,
    source: str,
) -> None:
    if source_store_id == target_store_id:
        return
    existing = conn.execute(
        """
        SELECT id, store_id
        FROM store_aliases
        WHERE raw_name = %s AND source = %s
        """,
        (raw_name, source),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO store_aliases (store_id, raw_name, source)
            VALUES (%s, %s, %s)
            """,
            (target_store_id, raw_name, source),
        )
        return
    if as_int(existing["store_id"]) == target_store_id:
        return
    conn.execute(
        "UPDATE store_aliases SET store_id = %s WHERE id = %s",
        (target_store_id, as_int(existing["id"])),
    )
