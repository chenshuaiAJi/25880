from decimal import Decimal

from psycopg import Connection

from app.domain.money import money_text, qty_text
from app.readers.values import (
    as_date,
    as_decimal,
    as_int,
    as_optional_decimal,
    as_optional_str,
    as_str,
    like_pattern,
)


def list_shipment_months(conn: Connection) -> list[dict[str, int]]:
    rows = conn.execute(
        """
        SELECT sf.year, sf.month, COUNT(o.id) AS order_count
        FROM shipment_orders o
        JOIN source_files sf ON sf.id = o.source_file_id
        GROUP BY sf.year, sf.month
        ORDER BY sf.year, sf.month
        """
    ).fetchall()
    return [
        {
            "year": as_int(row["year"]),
            "month": as_int(row["month"]),
            "orderCount": as_int(row["order_count"]),
        }
        for row in rows
    ]


def search_shipments(
    conn: Connection,
    year: int | None,
    month: int | None,
    date_from: object,
    date_to: object,
    batch_no: int | None,
    store_id: int | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict[str, object]:
    conditions = ["TRUE"]
    params: list[object] = []
    if year is not None:
        conditions.append("sf.year = %s")
        params.append(year)
    if month is not None:
        conditions.append("sf.month = %s")
        params.append(month)
    if date_from is not None:
        conditions.append("o.biz_date >= %s")
        params.append(date_from)
    if date_to is not None:
        conditions.append("o.biz_date <= %s")
        params.append(date_to)
    if batch_no is not None:
        conditions.append("sf.batch_no = %s")
        params.append(batch_no)
    if store_id is not None:
        conditions.append("o.store_id = %s")
        params.append(store_id)
    if keyword:
        conditions.append(
            "(s.display_name ILIKE %s ESCAPE '\\' OR o.customer_raw_name ILIKE %s ESCAPE '\\')"
        )
        pattern = like_pattern(keyword)
        params.extend([pattern, pattern])
    where_sql = " AND ".join(conditions)
    total_row = conn.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM shipment_orders o
        JOIN stores s ON s.id = o.store_id
        JOIN source_files sf ON sf.id = o.source_file_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()
    if total_row is None:
        raise RuntimeError("统计发货单失败")
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT
            o.id,
            o.biz_date,
            o.customer_raw_name,
            o.store_id,
            s.display_name,
            sf.file_name,
            sf.batch_no,
            sf.batch_label,
            sf.year,
            sf.month,
            COALESCE(SUM(l.amount), 0) AS total_amount,
            COUNT(l.id) AS line_count
        FROM shipment_orders o
        JOIN stores s ON s.id = o.store_id
        JOIN source_files sf ON sf.id = o.source_file_id
        LEFT JOIN shipment_lines l ON l.order_id = o.id
        WHERE {where_sql}
        GROUP BY o.id, s.display_name, sf.file_name, sf.batch_no, sf.batch_label, sf.year, sf.month
        ORDER BY o.biz_date DESC, sf.batch_no, o.order_index
        LIMIT %s OFFSET %s
        """,
        [*params, page_size, offset],
    ).fetchall()
    return {
        "page": page,
        "pageSize": page_size,
        "total": as_int(total_row["total"]),
        "items": [
            {
                "id": as_int(row["id"]),
                "bizDate": as_date(row["biz_date"]).isoformat(),
                "customerRawName": as_str(row["customer_raw_name"]),
                "storeId": as_int(row["store_id"]),
                "displayName": as_str(row["display_name"]),
                "fileName": as_str(row["file_name"]),
                "batchNo": as_int(row["batch_no"]),
                "batchLabel": as_str(row["batch_label"]),
                "year": as_int(row["year"]),
                "month": as_int(row["month"]),
                "totalAmount": money_text(as_decimal(row["total_amount"])),
                "lineCount": as_int(row["line_count"]),
            }
            for row in rows
        ],
    }


def get_shipment(conn: Connection, order_id: int) -> dict[str, object] | None:
    order = conn.execute(
        """
        SELECT
            o.id,
            o.biz_date,
            o.customer_raw_name,
            o.market_name,
            o.phone,
            o.address,
            o.price_ratio,
            o.ship_date_text,
            o.store_id,
            s.display_name,
            sf.file_name,
            sf.relative_path,
            sf.batch_no,
            sf.batch_label,
            sf.year,
            sf.month
        FROM shipment_orders o
        JOIN stores s ON s.id = o.store_id
        JOIN source_files sf ON sf.id = o.source_file_id
        WHERE o.id = %s
        """,
        (order_id,),
    ).fetchone()
    if order is None:
        return None
    lines = conn.execute(
        """
        SELECT
            line_index, product_name, unit, order_qty, ship_qty, gift_qty,
            weight_total, actual_weight, gift_weight, actual_qty, unit_price, amount
        FROM shipment_lines
        WHERE order_id = %s
        ORDER BY line_index
        """,
        (order_id,),
    ).fetchall()
    total = sum(
        (as_optional_decimal(line["amount"]) or Decimal("0") for line in lines),
        Decimal("0"),
    )
    return {
        "id": as_int(order["id"]),
        "bizDate": as_date(order["biz_date"]).isoformat(),
        "customerRawName": as_str(order["customer_raw_name"]),
        "displayName": as_str(order["display_name"]),
        "storeId": as_int(order["store_id"]),
        "marketName": as_optional_str(order["market_name"]),
        "phone": as_optional_str(order["phone"]),
        "address": as_optional_str(order["address"]),
        "priceRatio": as_optional_str(order["price_ratio"]),
        "shipDateText": as_optional_str(order["ship_date_text"]),
        "fileName": as_str(order["file_name"]),
        "relativePath": as_str(order["relative_path"]),
        "batchNo": as_int(order["batch_no"]),
        "batchLabel": as_str(order["batch_label"]),
        "year": as_int(order["year"]),
        "month": as_int(order["month"]),
        "totalAmount": money_text(total),
        "lines": [_line_payload(line) for line in lines],
    }


def _line_payload(line: dict[str, object]) -> dict[str, object]:
    return {
        "lineIndex": as_int(line["line_index"]),
        "productName": as_str(line["product_name"]),
        "unit": as_optional_str(line["unit"]),
        "orderQty": qty_text(as_optional_decimal(line["order_qty"])),
        "shipQty": qty_text(as_optional_decimal(line["ship_qty"])),
        "giftQty": qty_text(as_optional_decimal(line["gift_qty"])),
        "weightTotal": qty_text(as_optional_decimal(line["weight_total"])),
        "actualWeight": qty_text(as_optional_decimal(line["actual_weight"])),
        "giftWeight": qty_text(as_optional_decimal(line["gift_weight"])),
        "actualQty": qty_text(as_optional_decimal(line["actual_qty"])),
        "unitPrice": qty_text(as_optional_decimal(line["unit_price"])),
        "amount": money_text(amount) if (amount := as_optional_decimal(line["amount"])) is not None else None,
    }
