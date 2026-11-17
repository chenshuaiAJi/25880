from psycopg import Connection

from app.readers.values import as_date, as_int, as_optional_date, as_str


def ledger_stats(conn: Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM stores) AS stores,
            (SELECT COUNT(*) FROM shipment_orders) AS orders,
            (SELECT COUNT(*) FROM shipment_lines) AS lines,
            (SELECT COUNT(*) FROM remittance_sheets) AS sheets,
            (SELECT COUNT(*) FROM date_conflicts) AS conflicts,
            (SELECT COUNT(*) FROM import_warnings) AS warnings
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("统计失败")
    return {
        "stores": as_int(row["stores"]),
        "orders": as_int(row["orders"]),
        "lines": as_int(row["lines"]),
        "sheets": as_int(row["sheets"]),
        "conflicts": as_int(row["conflicts"]),
        "warnings": as_int(row["warnings"]),
    }


def list_conflicts(conn: Connection, page: int, page_size: int) -> dict[str, object]:
    total = _count(conn, "date_conflicts")
    offset = (page - 1) * page_size
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.cell_text,
            c.parsed_cell_date,
            c.biz_date,
            sf.file_name,
            sf.relative_path,
            sf.year,
            sf.month,
            sf.batch_no,
            sf.batch_label
        FROM date_conflicts c
        JOIN source_files sf ON sf.id = c.source_file_id
        ORDER BY c.biz_date, sf.relative_path
        LIMIT %s OFFSET %s
        """,
        (page_size, offset),
    ).fetchall()
    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "items": [
            {
                "id": as_int(row["id"]),
                "cellText": as_str(row["cell_text"]),
                "parsedCellDate": _iso(as_optional_date(row["parsed_cell_date"])),
                "bizDate": as_date(row["biz_date"]).isoformat(),
                "fileName": as_str(row["file_name"]),
                "relativePath": as_str(row["relative_path"]),
                "year": as_int(row["year"]),
                "month": as_int(row["month"]),
                "batchNo": as_int(row["batch_no"]),
                "batchLabel": as_str(row["batch_label"]),
            }
            for row in rows
        ],
    }


def list_warnings(conn: Connection, page: int, page_size: int) -> dict[str, object]:
    total = _count(conn, "import_warnings")
    offset = (page - 1) * page_size
    rows = conn.execute(
        """
        SELECT w.id, w.code, w.message, sf.file_name, sf.relative_path
        FROM import_warnings w
        LEFT JOIN source_files sf ON sf.id = w.source_file_id
        ORDER BY w.id
        LIMIT %s OFFSET %s
        """,
        (page_size, offset),
    ).fetchall()
    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "items": [
            {
                "id": as_int(row["id"]),
                "code": as_str(row["code"]),
                "message": as_str(row["message"]),
                "fileName": row["file_name"] if isinstance(row["file_name"], str) else None,
                "relativePath": row["relative_path"] if isinstance(row["relative_path"], str) else None,
            }
            for row in rows
        ],
    }


def _count(conn: Connection, table: str) -> int:
    if table not in {"date_conflicts", "import_warnings"}:
        raise ValueError("不允许的统计表")
    row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    if row is None:
        raise RuntimeError("统计失败")
    return as_int(row["total"])


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        text = value.isoformat()
        if isinstance(text, str):
            return text
    return None
