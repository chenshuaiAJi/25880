from datetime import date
from decimal import Decimal
from pathlib import Path

from psycopg import Connection

from app.importer.bank_parser import parse_bank_workbook
from app.services.bank import import_bank_file, remittance_gaps_for_matches, writeback_remittance_from_bank

BANK_FILE = Path(__file__).resolve().parents[2] / "file" / "银行回款" / "detail20261116.xlsx"


def test_parse_bank_detail_file() -> None:
    parsed = parse_bank_workbook(BANK_FILE)
    assert parsed.meta.account_name == "陈立君"
    assert parsed.meta.date_from == date(2026, 8, 16)
    assert parsed.meta.date_to == date(2026, 11, 16)
    assert len(parsed.transactions) == 111
    income = [item for item in parsed.transactions if item.direction == "in"]
    expense = [item for item in parsed.transactions if item.direction == "out"]
    assert len(income) == 59
    assert len(expense) == 52
    first = next(item for item in income if item.counterparty_name == "彭忠霞")
    assert first.amount == Decimal("49999.00")
    assert first.txn_date == date(2026, 11, 15)


def test_import_and_writeback(conn: Connection) -> None:
    store = conn.execute(
        "INSERT INTO stores (display_name, manager_name) VALUES ('历庄-大嘉超市专柜', '彭忠霞') RETURNING id"
    ).fetchone()
    assert store is not None
    store_id = int(store["id"])
    conn.execute(
        "INSERT INTO store_aliases (store_id, raw_name, source) VALUES (%s, '彭忠霞-大嘉超市厉庄专柜', 'shipment')",
        (store_id,),
    )
    sheet = conn.execute(
        "INSERT INTO remittance_sheets (year, month, day_count) VALUES (2026, 11, 30) RETURNING id"
    ).fetchone()
    assert sheet is not None
    row = conn.execute(
        """
        INSERT INTO remittance_rows (sheet_id, store_id, row_index, imported_raw_name, opening_balance)
        VALUES (%s, %s, 1, '历庄-大嘉超市专柜', 0)
        RETURNING id
        """,
        (sheet["id"], store_id),
    ).fetchone()
    assert row is not None
    conn.execute(
        "INSERT INTO remittance_cells (row_id, day, kind, amount) VALUES (%s, 15, 'remit', 1000)",
        (row["id"],),
    )

    result = import_bank_file(conn, BANK_FILE, BANK_FILE.parent)
    assert result["inserted"] == 111
    assert int(result["suggested"]) >= 1

    txn = conn.execute(
        """
        SELECT id, store_id, match_status
        FROM bank_transactions
        WHERE counterparty_name = '彭忠霞' AND amount = 49999 AND txn_date = '2026-11-15'
        """
    ).fetchone()
    assert txn is not None
    assert int(txn["store_id"]) == store_id
    assert txn["match_status"] == "suggested"
    conn.execute(
        "UPDATE bank_transactions SET match_status = 'confirmed' WHERE id = %s",
        (txn["id"],),
    )

    gaps = remittance_gaps_for_matches(conn, 2026, 11)
    assert any(item["storeId"] == store_id and item["difference"] == "48999.00" for item in gaps)

    written = writeback_remittance_from_bank(conn, store_id, date(2026, 11, 15))
    assert written["amount"] == "49999.00"
    cell = conn.execute(
        "SELECT amount FROM remittance_cells WHERE row_id = %s AND day = 15 AND kind = 'remit'",
        (row["id"],),
    ).fetchone()
    assert cell is not None
    assert cell["amount"] == Decimal("49999.00")
