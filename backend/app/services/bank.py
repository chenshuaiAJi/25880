from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from psycopg import Connection

from app.config import REPO_ROOT
from app.domain.money import money_text
from app.errors import AppError
from app.importer.bank_parser import parse_bank_workbook
from app.readers.values import as_date, as_decimal, as_int, as_optional_date, as_optional_str, as_str
from app.services.remittances import update_remittance_cell


def default_bank_root() -> Path:
    return REPO_ROOT / "file" / "银行回款"


def import_bank_file(conn: Connection, path: Path, root: Path | None = None) -> dict[str, object]:
    if not path.is_file():
        raise AppError(f"找不到银行明细文件：{path}")
    base = root or path.parent
    relative = path.relative_to(base).as_posix() if path.is_relative_to(base) else path.name
    parsed = parse_bank_workbook(path)
    existing = conn.execute(
        "SELECT id FROM bank_import_batches WHERE relative_path = %s",
        (relative,),
    ).fetchone()
    if existing is not None:
        conn.execute("DELETE FROM bank_import_batches WHERE id = %s", (as_int(existing["id"]),))
    batch = conn.execute(
        """
        INSERT INTO bank_import_batches (
            relative_path, file_name, account_mask, account_name, date_from, date_to
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            relative,
            path.name,
            parsed.meta.account_mask,
            parsed.meta.account_name,
            parsed.meta.date_from,
            parsed.meta.date_to,
        ),
    ).fetchone()
    if batch is None:
        raise AppError("写入银行导入批次失败")
    batch_id = as_int(batch["id"])
    inserted = 0
    skipped = 0
    for txn in parsed.transactions:
        conflict = conn.execute(
            "SELECT id FROM bank_transactions WHERE external_uid = %s",
            (txn.external_uid,),
        ).fetchone()
        if conflict is not None:
            skipped += 1
            continue
        conn.execute(
            """
            INSERT INTO bank_transactions (
                batch_id, external_uid, txn_date, txn_time, amount, direction, balance_after,
                counterparty_name, counterparty_account, bank_name, channel, txn_type,
                purpose, memo, match_status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, 'unmatched'
            )
            """,
            (
                batch_id,
                txn.external_uid,
                txn.txn_date,
                txn.txn_time,
                txn.amount,
                txn.direction,
                txn.balance_after,
                txn.counterparty_name,
                txn.counterparty_account,
                txn.bank_name,
                txn.channel,
                txn.txn_type,
                txn.purpose,
                txn.memo,
            ),
        )
        inserted += 1
    suggested = suggest_matches(conn, batch_id)
    return {
        "batchId": batch_id,
        "fileName": path.name,
        "inserted": inserted,
        "skippedDuplicates": skipped,
        "suggested": suggested,
        "incomeCount": sum(1 for item in parsed.transactions if item.direction == "in"),
        "expenseCount": sum(1 for item in parsed.transactions if item.direction == "out"),
    }


def suggest_matches(conn: Connection, batch_id: int | None = None) -> int:
    stores = conn.execute(
        """
        SELECT
            s.id,
            s.display_name,
            s.manager_name,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT a.raw_name), NULL) AS aliases
        FROM stores s
        LEFT JOIN store_aliases a ON a.store_id = s.id
        GROUP BY s.id
        """
    ).fetchall()
    store_profiles: list[tuple[int, set[str]]] = []
    for store in stores:
        names = {as_str(store["display_name"])}
        manager = store["manager_name"]
        if isinstance(manager, str) and manager.strip():
            names.add(manager.strip())
        aliases = store["aliases"]
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    names.add(alias.strip())
        store_profiles.append((as_int(store["id"]), names))

    query = """
        SELECT id, txn_date, amount, counterparty_name, match_status
        FROM bank_transactions
        WHERE direction = 'in'
          AND match_status IN ('unmatched', 'suggested')
    """
    params: list[object] = []
    if batch_id is not None:
        query += " AND batch_id = %s"
        params.append(batch_id)
    txns = conn.execute(query, params).fetchall()
    updated = 0
    for txn in txns:
        counterparty = as_optional_str(txn["counterparty_name"])
        if not counterparty:
            continue
        store_id = _best_store(counterparty, store_profiles)
        if store_id is None:
            continue
        conn.execute(
            """
            UPDATE bank_transactions
            SET store_id = %s,
                matched_date = %s,
                match_status = 'suggested'
            WHERE id = %s
            """,
            (store_id, as_date(txn["txn_date"]), as_int(txn["id"])),
        )
        updated += 1
    return updated


def list_bank_transactions(
    conn: Connection,
    *,
    direction: str | None,
    match_status: str | None,
    page: int,
    page_size: int,
) -> dict[str, object]:
    conditions = ["TRUE"]
    params: list[object] = []
    if direction in {"in", "out"}:
        conditions.append("t.direction = %s")
        params.append(direction)
    if match_status:
        conditions.append("t.match_status = %s")
        params.append(match_status)
    where_sql = " AND ".join(conditions)
    total_row = conn.execute(
        f"SELECT COUNT(*) AS total FROM bank_transactions t WHERE {where_sql}",
        params,
    ).fetchone()
    if total_row is None:
        raise AppError("统计银行流水失败")
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT
            t.id, t.txn_date, t.txn_time, t.amount, t.direction, t.counterparty_name,
            t.purpose, t.memo, t.match_status, t.matched_date, t.store_id,
            s.display_name
        FROM bank_transactions t
        LEFT JOIN stores s ON s.id = t.store_id
        WHERE {where_sql}
        ORDER BY t.txn_date DESC, t.txn_time DESC NULLS LAST, t.id DESC
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
                "txnDate": as_date(row["txn_date"]).isoformat(),
                "txnTime": row["txn_time"].isoformat(timespec="seconds") if row["txn_time"] is not None else None,
                "amount": money_text(as_decimal(row["amount"])),
                "direction": as_str(row["direction"]),
                "counterpartyName": as_optional_str(row["counterparty_name"]),
                "purpose": as_optional_str(row["purpose"]),
                "memo": as_optional_str(row["memo"]),
                "matchStatus": as_str(row["match_status"]),
                "matchedDate": as_optional_date(row["matched_date"]).isoformat()
                if as_optional_date(row["matched_date"]) is not None
                else None,
                "storeId": as_int(row["store_id"]) if row["store_id"] is not None else None,
                "displayName": as_optional_str(row["display_name"]),
            }
            for row in rows
        ],
    }


def assign_bank_transaction(
    conn: Connection,
    txn_id: int,
    store_id: int,
    matched_date: date,
    *,
    confirm: bool,
) -> dict[str, object]:
    txn = conn.execute("SELECT id, direction FROM bank_transactions WHERE id = %s", (txn_id,)).fetchone()
    if txn is None:
        raise AppError("找不到这笔流水", status_code=404, code="NOT_FOUND")
    if as_str(txn["direction"]) != "in":
        raise AppError("支出流水不能匹配到门店汇款")
    store = conn.execute("SELECT 1 FROM stores WHERE id = %s", (store_id,)).fetchone()
    if store is None:
        raise AppError("找不到门店", status_code=404, code="NOT_FOUND")
    status = "confirmed" if confirm else "suggested"
    conn.execute(
        """
        UPDATE bank_transactions
        SET store_id = %s, matched_date = %s, match_status = %s
        WHERE id = %s
        """,
        (store_id, matched_date, status, txn_id),
    )
    return {"id": txn_id, "storeId": store_id, "matchedDate": matched_date.isoformat(), "matchStatus": status}


def remittance_gaps_for_matches(conn: Connection, year: int, month: int) -> list[dict[str, object]]:
    """已确认归属流水合计 vs 汇款表当天汇款。"""
    rows = conn.execute(
        """
        SELECT
            t.store_id,
            t.matched_date,
            s.display_name,
            SUM(t.amount) AS bank_total
        FROM bank_transactions t
        JOIN stores s ON s.id = t.store_id
        WHERE t.direction = 'in'
          AND t.match_status = 'confirmed'
          AND t.store_id IS NOT NULL
          AND t.matched_date IS NOT NULL
          AND EXTRACT(YEAR FROM t.matched_date) = %s
          AND EXTRACT(MONTH FROM t.matched_date) = %s
        GROUP BY t.store_id, t.matched_date, s.display_name
        ORDER BY t.matched_date, s.display_name
        """,
        (year, month),
    ).fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        store_id = as_int(row["store_id"])
        matched_date = as_date(row["matched_date"])
        bank_total = as_decimal(row["bank_total"])
        remit = _remittance_day_amount(conn, store_id, matched_date, "remit")
        remit_amount = remit if remit is not None else Decimal("0.00")
        difference = bank_total - remit_amount
        if difference == 0:
            continue
        items.append(
            {
                "storeId": store_id,
                "displayName": as_str(row["display_name"]),
                "date": matched_date.isoformat(),
                "bankTotal": money_text(bank_total),
                "remitAmount": money_text(remit_amount) if remit is not None else None,
                "difference": money_text(difference),
            }
        )
    return items


def writeback_remittance_from_bank(
    conn: Connection,
    store_id: int,
    matched_date: date,
) -> dict[str, object]:
    total_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM bank_transactions
        WHERE store_id = %s
          AND matched_date = %s
          AND direction = 'in'
          AND match_status = 'confirmed'
        """,
        (store_id, matched_date),
    ).fetchone()
    if total_row is None:
        raise AppError("统计流水失败")
    total = as_decimal(total_row["total"])
    remittance_row = conn.execute(
        """
        SELECT r.id
        FROM remittance_rows r
        JOIN remittance_sheets s ON s.id = r.sheet_id
        WHERE r.store_id = %s AND s.year = %s AND s.month = %s
        """,
        (store_id, matched_date.year, matched_date.month),
    ).fetchone()
    if remittance_row is None:
        raise AppError("该店这个月没有汇款行，无法回写")
    sheet = update_remittance_cell(
        conn,
        as_int(remittance_row["id"]),
        matched_date.day,
        "remit",
        money_text(total),
    )
    return {"storeId": store_id, "date": matched_date.isoformat(), "amount": money_text(total), "sheet": sheet}


def _remittance_day_amount(conn: Connection, store_id: int, day: date, kind: str) -> Decimal | None:
    row = conn.execute(
        """
        SELECT c.amount
        FROM remittance_cells c
        JOIN remittance_rows r ON r.id = c.row_id
        JOIN remittance_sheets s ON s.id = r.sheet_id
        WHERE r.store_id = %s
          AND s.year = %s
          AND s.month = %s
          AND c.day = %s
          AND c.kind = %s
        """,
        (store_id, day.year, day.month, day.day, kind),
    ).fetchone()
    if row is None:
        return None
    return as_decimal(row["amount"])


def _best_store(counterparty: str, profiles: list[tuple[int, set[str]]]) -> int | None:
    # 对方户名常是负责人姓名；优先精确命中经理名/别名中的片段。
    exact: list[int] = []
    fuzzy: list[int] = []
    for store_id, names in profiles:
        for name in names:
            if counterparty == name or counterparty in name or name in counterparty:
                if counterparty == name or name.endswith(counterparty) or counterparty.endswith(name):
                    exact.append(store_id)
                else:
                    fuzzy.append(store_id)
                break
    if len(set(exact)) == 1:
        return exact[0]
    if len(set(fuzzy)) == 1 and not exact:
        return fuzzy[0]
    return None


def nearby_dates(center: date) -> list[date]:
    return [center - timedelta(days=1), center, center + timedelta(days=1)]
