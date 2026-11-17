from psycopg import Connection

from app.readers.values import as_int, as_optional_str, as_str, like_pattern


def list_stores(conn: Connection, keyword: str | None) -> list[dict[str, object]]:
    conditions = ["TRUE"]
    params: list[object] = []
    if keyword:
        conditions.append(
            """
            (
                s.display_name ILIKE %s ESCAPE '\\'
                OR EXISTS (
                    SELECT 1 FROM store_aliases a
                    WHERE a.store_id = s.id AND a.raw_name ILIKE %s ESCAPE '\\'
                )
            )
            """
        )
        pattern = like_pattern(keyword)
        params.extend([pattern, pattern])
    where_sql = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT
            s.id,
            s.display_name,
            s.code,
            s.manager_name,
            s.phone,
            s.address,
            (SELECT COUNT(*) FROM shipment_orders o WHERE o.store_id = s.id) AS order_count,
            (SELECT COUNT(*) FROM remittance_rows r WHERE r.store_id = s.id) AS remittance_row_count
        FROM stores s
        WHERE {where_sql}
        ORDER BY s.display_name
        """,
        params,
    ).fetchall()
    return [_store_summary(row) for row in rows]


def get_store(conn: Connection, store_id: int) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT
            s.id,
            s.display_name,
            s.code,
            s.manager_name,
            s.phone,
            s.address,
            (SELECT COUNT(*) FROM shipment_orders o WHERE o.store_id = s.id) AS order_count,
            (SELECT COUNT(*) FROM remittance_rows r WHERE r.store_id = s.id) AS remittance_row_count
        FROM stores s
        WHERE s.id = %s
        """,
        (store_id,),
    ).fetchone()
    if row is None:
        return None
    aliases = conn.execute(
        """
        SELECT
            a.raw_name,
            a.source,
            CASE
                WHEN a.source = 'shipment' THEN (
                    SELECT COUNT(*)
                    FROM shipment_orders o
                    WHERE o.store_id = a.store_id AND o.customer_raw_name = a.raw_name
                )
                ELSE (
                    SELECT COUNT(*)
                    FROM remittance_rows r
                    WHERE r.store_id = a.store_id AND r.imported_raw_name = a.raw_name
                )
            END AS document_count
        FROM store_aliases a
        WHERE a.store_id = %s
        ORDER BY a.source, a.raw_name
        """,
        (store_id,),
    ).fetchall()
    payload = _store_summary(row)
    payload["aliases"] = [
        {
            "rawName": as_str(alias["raw_name"]),
            "source": as_str(alias["source"]),
            "documentCount": as_int(alias["document_count"]),
        }
        for alias in aliases
    ]
    return payload


def _store_summary(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": as_int(row["id"]),
        "displayName": as_str(row["display_name"]),
        "code": as_optional_str(row["code"]),
        "managerName": as_optional_str(row["manager_name"]),
        "phone": as_optional_str(row["phone"]),
        "address": as_optional_str(row["address"]),
        "orderCount": as_int(row["order_count"]),
        "remittanceRowCount": as_int(row["remittance_row_count"]),
    }
