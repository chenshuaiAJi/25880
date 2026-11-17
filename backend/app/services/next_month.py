from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.domain.balance import month_balance
from app.domain.money import money_text
from app.domain.month_nav import month_has_ended, next_year_month, previous_year_month, template_day_count
from app.errors import AppError
from app.readers.remittances import get_remittance_sheet, list_remittance_months
from app.readers.values import as_decimal, as_int, as_str


def preview_create_next_month(
    conn: Connection,
    year: int,
    month: int,
    today: date | None = None,
) -> dict[str, object]:
    today = today or date.today()
    current = conn.execute(
        """
        SELECT id, year, month, day_count
        FROM remittance_sheets
        WHERE year = %s AND month = %s
        """,
        (year, month),
    ).fetchone()
    if current is None:
        raise AppError("这个月还没有汇款表", status_code=404, code="NOT_FOUND")
    next_year, next_month = next_year_month(year, month)
    exists = conn.execute(
        """
        SELECT 1 FROM remittance_sheets WHERE year = %s AND month = %s
        """,
        (next_year, next_month),
    ).fetchone()
    can_create = True
    blockers: list[str] = []
    if not month_has_ended(year, month, today):
        can_create = False
        blockers.append(f"{year}年{month}月还没结束，不能创建下月报表")
    if exists is not None:
        can_create = False
        blockers.append(f"{next_year}年{next_month}月报表已经存在")
    opening_gaps = _opening_gaps(conn, year, month)
    stores = _current_store_balances(conn, as_int(current["id"]))
    return {
        "sourceYear": year,
        "sourceMonth": month,
        "targetYear": next_year,
        "targetMonth": next_month,
        "targetDayCount": template_day_count(next_year, next_month),
        "canCreate": can_create,
        "blockers": blockers,
        "message": f"根据 {year} 年 {month} 月，创建 {next_year} 年 {next_month} 月报表",
        "storeCount": len(stores),
        "stores": stores,
        "openingGaps": opening_gaps,
    }


def create_next_month(
    conn: Connection,
    year: int,
    month: int,
    *,
    continue_with_gaps: bool = False,
    today: date | None = None,
) -> dict[str, object]:
    preview = preview_create_next_month(conn, year, month, today=today)
    if not preview["canCreate"]:
        blockers = preview["blockers"]
        message = blockers[0] if isinstance(blockers, list) and blockers else "不能创建下月报表"
        raise AppError(str(message))
    gaps = preview["openingGaps"]
    if isinstance(gaps, list) and gaps and not continue_with_gaps:
        raise AppError(
            "上一期与再上一期期初仍不平，请先确认是否继续",
            status_code=409,
            code="OPENING_GAP",
        )
    current = conn.execute(
        """
        SELECT id
        FROM remittance_sheets
        WHERE year = %s AND month = %s
        """,
        (year, month),
    ).fetchone()
    if current is None:
        raise AppError("这个月还没有汇款表", status_code=404, code="NOT_FOUND")
    next_year = int(preview["targetYear"])  # type: ignore[arg-type]
    next_month = int(preview["targetMonth"])  # type: ignore[arg-type]
    day_count = int(preview["targetDayCount"])  # type: ignore[arg-type]
    sheet = conn.execute(
        """
        INSERT INTO remittance_sheets (source_file_id, year, month, day_count)
        VALUES (NULL, %s, %s, %s)
        RETURNING id
        """,
        (next_year, next_month, day_count),
    ).fetchone()
    if sheet is None:
        raise AppError("创建下月报表失败")
    sheet_id = as_int(sheet["id"])
    rows = conn.execute(
        """
        SELECT
            r.store_id,
            r.imported_raw_name,
            r.opening_balance,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'remit'), 0) AS remit_total,
            COALESCE(SUM(c.amount) FILTER (WHERE c.kind = 'ship'), 0) AS ship_total,
            s.display_name
        FROM remittance_rows r
        JOIN stores s ON s.id = r.store_id
        LEFT JOIN remittance_cells c ON c.row_id = r.id
        WHERE r.sheet_id = %s
        GROUP BY r.id, s.display_name
        ORDER BY r.row_index
        """,
        (as_int(current["id"]),),
    ).fetchall()
    for index, row in enumerate(rows, start=1):
        opening = month_balance(
            as_decimal(row["opening_balance"]),
            as_decimal(row["remit_total"]),
            as_decimal(row["ship_total"]),
        )
        conn.execute(
            """
            INSERT INTO remittance_rows (
                sheet_id, store_id, row_index, imported_raw_name, opening_balance
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                sheet_id,
                as_int(row["store_id"]),
                index,
                as_str(row["display_name"]),
                opening,
            ),
        )
    created = get_remittance_sheet(conn, next_year, next_month)
    if created is None:
        raise AppError("创建下月报表后读取失败")
    return {
        "preview": preview,
        "sheet": created,
        "months": list_remittance_months(conn),
    }


def list_opening_mismatches(conn: Connection, year: int, month: int) -> list[dict[str, object]]:
    """本月期初应等于上月余额。列出不平门店。"""
    prev_year, prev_month = previous_year_month(year, month)
    rows = conn.execute(
        """
        SELECT
            curr.store_id,
            st.display_name,
            curr.opening_balance AS current_opening,
            prev.opening_balance AS prev_opening,
            COALESCE(SUM(pc.amount) FILTER (WHERE pc.kind = 'remit'), 0) AS prev_remit,
            COALESCE(SUM(pc.amount) FILTER (WHERE pc.kind = 'ship'), 0) AS prev_ship
        FROM remittance_rows curr
        JOIN remittance_sheets cs ON cs.id = curr.sheet_id
        JOIN stores st ON st.id = curr.store_id
        LEFT JOIN remittance_sheets ps
          ON ps.year = %s AND ps.month = %s
        LEFT JOIN remittance_rows prev
          ON prev.sheet_id = ps.id AND prev.store_id = curr.store_id
        LEFT JOIN remittance_cells pc ON pc.row_id = prev.id
        WHERE cs.year = %s AND cs.month = %s
        GROUP BY curr.id, st.display_name, prev.opening_balance
        ORDER BY st.display_name
        """,
        (prev_year, prev_month, year, month),
    ).fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        if row["prev_opening"] is None:
            continue
        previous_balance = month_balance(
            as_decimal(row["prev_opening"]),
            as_decimal(row["prev_remit"]),
            as_decimal(row["prev_ship"]),
        )
        current_opening = as_decimal(row["current_opening"])
        if previous_balance == current_opening:
            continue
        items.append(
            {
                "storeId": as_int(row["store_id"]),
                "displayName": as_str(row["display_name"]),
                "previousBalance": money_text(previous_balance),
                "currentOpening": money_text(current_opening),
                "difference": money_text(previous_balance - current_opening),
            }
        )
    return items


def apply_opening_from_previous(conn: Connection, year: int, month: int, store_ids: list[int] | None) -> dict[str, object]:
    mismatches = list_opening_mismatches(conn, year, month)
    selected = set(store_ids) if store_ids else None
    updated = 0
    for item in mismatches:
        store_id = int(item["storeId"])  # type: ignore[arg-type]
        if selected is not None and store_id not in selected:
            continue
        conn.execute(
            """
            UPDATE remittance_rows r
            SET opening_balance = %s
            FROM remittance_sheets s
            WHERE r.sheet_id = s.id
              AND s.year = %s
              AND s.month = %s
              AND r.store_id = %s
            """,
            (Decimal(str(item["previousBalance"])), year, month, store_id),
        )
        updated += 1
    sheet = get_remittance_sheet(conn, year, month)
    if sheet is None:
        raise AppError("找不到汇款月表", status_code=404, code="NOT_FOUND")
    return {"updated": updated, "sheet": sheet, "remaining": list_opening_mismatches(conn, year, month)}


def _current_store_balances(conn: Connection, sheet_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            r.store_id,
            s.display_name,
            r.opening_balance,
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
    items: list[dict[str, object]] = []
    for row in rows:
        balance = month_balance(
            as_decimal(row["opening_balance"]),
            as_decimal(row["remit_total"]),
            as_decimal(row["ship_total"]),
        )
        items.append(
            {
                "storeId": as_int(row["store_id"]),
                "displayName": as_str(row["display_name"]),
                "openingBalance": money_text(balance),
            }
        )
    return items


def _opening_gaps(conn: Connection, year: int, month: int) -> list[dict[str, object]]:
    """创建下月前，检查当前月相对再上一期是否仍有期初不平。"""
    return list_opening_mismatches(conn, year, month)
