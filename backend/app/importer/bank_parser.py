"""农行账户明细：前两行账户信息，第 3 行表头，其后为明细。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.money import MONEY

_ACCOUNT_LINE = re.compile(
    r"账户[:：]\s*(?P<account>[^\s]+)\s+户名[:：]\s*(?P<name>\S+)\s+起始日期[:：]\s*(?P<start>\d{8})\s+截止日期[:：]\s*(?P<end>\d{8})"
)


@dataclass(frozen=True)
class BankBatchMeta:
    account_mask: str | None
    account_name: str | None
    date_from: date | None
    date_to: date | None


@dataclass(frozen=True)
class ParsedBankTxn:
    external_uid: str
    txn_date: date
    txn_time: time | None
    amount: Decimal
    direction: str
    balance_after: Decimal | None
    counterparty_name: str | None
    counterparty_account: str | None
    bank_name: str | None
    channel: str | None
    txn_type: str | None
    purpose: str | None
    memo: str | None


@dataclass
class ParsedBankFile:
    meta: BankBatchMeta
    transactions: list[ParsedBankTxn]


def parse_bank_workbook(path: Path) -> ParsedBankFile:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        meta = _parse_meta(sheet)
        header_row = _find_header_row(sheet)
        columns = _map_columns(sheet, header_row)
        transactions: list[ParsedBankTxn] = []
        for row_index in range(header_row + 1, sheet.max_row + 1):
            txn = _parse_row(sheet, row_index, columns)
            if txn is not None:
                transactions.append(txn)
        return ParsedBankFile(meta=meta, transactions=transactions)
    finally:
        workbook.close()


def _parse_meta(sheet: Worksheet) -> BankBatchMeta:
    account_mask = None
    account_name = None
    date_from = None
    date_to = None
    for row_index in range(1, min(4, sheet.max_row + 1)):
        text = _cell_text(sheet.cell(row_index, 1).value)
        if "账户" not in text or "户名" not in text:
            continue
        matched = _ACCOUNT_LINE.search(text)
        if matched is not None:
            account_mask = matched.group("account")
            account_name = matched.group("name")
            date_from = _parse_compact_date(matched.group("start"))
            date_to = _parse_compact_date(matched.group("end"))
            break
        account_mask = _between(text, "账户：", "户名") or _between(text, "账户:", "户名")
        account_name = _between(text, "户名：", "起始日期") or _between(text, "户名:", "起始日期")
        start = _between(text, "起始日期：", "截止日期") or _between(text, "起始日期:", "截止日期")
        end_token = "截止日期：" if "截止日期：" in text else "截止日期:"
        end = text.split(end_token)[-1].strip() if end_token in text else None
        date_from = _parse_compact_date(start)
        date_to = _parse_compact_date(end)
        break
    return BankBatchMeta(account_mask, account_name, date_from, date_to)


def _find_header_row(sheet: Worksheet) -> int:
    for row_index in range(1, min(8, sheet.max_row + 1)):
        values = [_cell_text(sheet.cell(row_index, col).value) for col in range(1, 12)]
        if "交易日期" in values and "交易金额" in values:
            return row_index
    raise ValueError("找不到银行明细表头")


def _map_columns(sheet: Worksheet, header_row: int) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for col in range(1, sheet.max_column + 1):
        header = _cell_text(sheet.cell(header_row, col).value)
        if header == "交易日期":
            mapping["date"] = col
        elif header == "交易时间":
            mapping["time"] = col
        elif header == "交易金额":
            mapping["amount"] = col
        elif header == "本次余额":
            mapping["balance"] = col
        elif header == "对方户名":
            mapping["counterparty"] = col
        elif header == "对方账号":
            mapping["account"] = col
        elif header == "交易行":
            mapping["bank"] = col
        elif header == "交易渠道":
            mapping["channel"] = col
        elif header == "交易类型":
            mapping["txn_type"] = col
        elif header == "交易用途":
            mapping["purpose"] = col
        elif header == "交易摘要":
            mapping["memo"] = col
    if "date" not in mapping or "amount" not in mapping:
        raise ValueError("银行明细缺少交易日期或交易金额列")
    return mapping


def _parse_row(sheet: Worksheet, row_index: int, columns: dict[str, int]) -> ParsedBankTxn | None:
    date_value = sheet.cell(row_index, columns["date"]).value
    amount_value = sheet.cell(row_index, columns["amount"]).value
    if date_value in (None, "") and amount_value in (None, ""):
        return None
    txn_date = _parse_date(date_value)
    if txn_date is None:
        return None
    amount, direction = _parse_signed_amount(amount_value)
    if amount is None or direction is None:
        return None
    txn_time = _parse_time(sheet.cell(row_index, columns["time"]).value) if "time" in columns else None
    counterparty = _optional_text(sheet, row_index, columns.get("counterparty"))
    account = _optional_text(sheet, row_index, columns.get("account"))
    purpose = _optional_text(sheet, row_index, columns.get("purpose"))
    memo = _optional_text(sheet, row_index, columns.get("memo"))
    uid_source = "|".join(
        [
            txn_date.isoformat(),
            txn_time.isoformat(timespec="seconds") if txn_time else "",
            f"{direction}{amount}",
            account or "",
            counterparty or "",
            purpose or "",
            memo or "",
            str(row_index),
        ]
    )
    external_uid = hashlib.sha256(uid_source.encode("utf-8")).hexdigest()
    return ParsedBankTxn(
        external_uid=external_uid,
        txn_date=txn_date,
        txn_time=txn_time,
        amount=amount,
        direction=direction,
        balance_after=_parse_plain_amount(
            sheet.cell(row_index, columns["balance"]).value if "balance" in columns else None
        ),
        counterparty_name=counterparty,
        counterparty_account=account,
        bank_name=_optional_text(sheet, row_index, columns.get("bank")),
        channel=_optional_text(sheet, row_index, columns.get("channel")),
        txn_type=_optional_text(sheet, row_index, columns.get("txn_type")),
        purpose=purpose,
        memo=memo,
    )


def _parse_signed_amount(value: object) -> tuple[Decimal | None, str | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value)).quantize(MONEY)
        if amount > 0:
            return amount, "in"
        if amount < 0:
            return abs(amount), "out"
        return Decimal("0.00"), "in"
    text = str(value).replace(",", "").strip()
    if text == "":
        return None, None
    direction = "in"
    if text.startswith("+"):
        text = text[1:]
        direction = "in"
    elif text.startswith("-"):
        text = text[1:]
        direction = "out"
    try:
        amount = Decimal(text).quantize(MONEY)
    except InvalidOperation:
        return None, None
    return amount, direction


def _parse_plain_amount(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("+", "")).quantize(MONEY)
    except InvalidOperation:
        return None


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _cell_text(value)
    if text == "":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(value: object) -> time | None:
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    text = _cell_text(value)
    if text == "":
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _parse_compact_date(text: str | None) -> date | None:
    if text is None:
        return None
    cleaned = text.strip()
    if len(cleaned) < 8:
        return None
    try:
        return datetime.strptime(cleaned[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _optional_text(sheet: Worksheet, row_index: int, col: int | None) -> str | None:
    if col is None:
        return None
    text = _cell_text(sheet.cell(row_index, col).value)
    return text or None


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _between(text: str, left: str, right: str) -> str | None:
    if left not in text or right not in text:
        return None
    return text.split(left, 1)[1].split(right, 1)[0].strip() or None
