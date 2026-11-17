from decimal import Decimal

from psycopg import Connection

from app.domain.balance import month_balance
from app.domain.calendar_util import calendar_day_count
from app.domain.money import money_text
from app.readers.values import as_decimal, as_int, as_str


def list_remittance_months(conn: Connection) -> list[dict[str, int]]:
    rows = conn.execute(
        """
        SELECT year, month, day_count
        FROM remittance_sheets
        ORDER BY year, month
        """
    ).fetchall()
    return [
        {"year": as_int(row["year"]), "month": as_int(row["month"]), "dayCount": as_int(row["day_count"])}
        for row in rows
    ]


def get_remittance_sheet(conn: Connection, year: int, month: int) -> dict[str, object] | None:
    sheet = conn.execute(
        """
        SELECT id, year, month, day_count
        FROM remittance_sheets
        WHERE year = %s AND month = %s
        """,
        (year, month),
    ).fetchone()
    if sheet is None:
        return None
    sheet_id = as_int(sheet["id"])
    row_records = conn.execute(
        """
        SELECT
            r.id,
            r.store_id,
            r.imported_raw_name,
            r.opening_balance,
            s.display_name,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'remit'), 0) AS remit_total,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'ship'), 0) AS ship_total
        FROM remittance_rows r
        JOIN stores s ON s.id = r.store_id
        LEFT JOIN remittance_cells c ON c.row_id = r.id
        WHERE r.sheet_id = %s
        GROUP BY r.id, s.display_name
        ORDER BY r.row_index
        """,
        (sheet_id,),
    ).fetchall()
    cell_records = conn.execute(
        """
        SELECT c.row_id, c.day, c.kind, c.amount
        FROM remittance_cells c
        JOIN remittance_rows r ON r.id = c.row_id
        WHERE r.sheet_id = %s
        """,
        (sheet_id,),
    ).fetchall()
    grouped: dict[int, dict[str, dict[str, str | None]]] = {}
    for cell in cell_records:
        row_id = as_int(cell["row_id"])
        day_key = str(as_int(cell["day"]))
        kind = as_str(cell["kind"])
        bucket = grouped.setdefault(row_id, {})
        day_bucket = bucket.setdefault(day_key, {"remit": None, "ship": None})
        if kind in day_bucket:
            day_bucket[kind] = money_text(as_decimal(cell["amount"]))
    items: list[dict[str, object]] = []
    for row in row_records:
        opening = as_decimal(row["opening_balance"])
        remit_total = as_decimal(row["remit_total"])
        ship_total = as_decimal(row["ship_total"])
        balance = month_balance(opening, remit_total, ship_total)
        items.append(
            {
                "id": as_int(row["id"]),
                "storeId": as_int(row["store_id"]),
                "displayName": as_str(row["display_name"]),
                "importedRawName": as_str(row["imported_raw_name"]),
                "openingBalance": money_text(opening),
                "remitTotal": money_text(remit_total),
                "shipTotal": money_text(ship_total),
                "balance": money_text(balance),
                "cells": grouped.get(as_int(row["id"]), {}),
            }
        )
    return {
        "year": as_int(sheet["year"]),
        "month": as_int(sheet["month"]),
        "dayCount": as_int(sheet["day_count"]),
        "calendarDays": calendar_day_count(year, month),
        "rows": items,
    }
