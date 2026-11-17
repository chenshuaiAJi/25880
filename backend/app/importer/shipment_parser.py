"""发货单是打印稿。按「订单汇总表 / 客户名称 / 产品名称」定位，不写死行号。"""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from xlrd.sheet import Sheet

from app.domain.balance import sum_money
from app.domain.money import money_from_excel, qty_from_excel
from app.importer.models import (
    ParsedConflict,
    ParsedLine,
    ParsedOrder,
    ParsedShipment,
    ParseWarning,
    cell_text,
    workbook_sheet,
)

_LABELS = ("市场名称", "电话", "发货日期", "客户名称", "详细地址", "价格比率")
_CELL_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_shipment_workbook(path: Path, biz_date: date, span_end: date) -> ParsedShipment:
    sheet = workbook_sheet(path)
    orders: list[ParsedOrder] = []
    warnings: list[ParseWarning] = []
    conflicts: dict[date, ParsedConflict] = {}
    current: ParsedOrder | None = None
    columns: dict[str, int] | None = None

    for row_index in range(sheet.nrows):
        pairs = _nonempty_texts(sheet, row_index)
        if not pairs:
            continue
        texts = [text for _col, text in pairs]
        if any("订单汇总表" in text for text in texts):
            _flush(current, orders, warnings)
            current = ParsedOrder(customer_raw_name="")
            columns = None
            continue
        if current is None:
            continue
        if any("产品名称" in text for text in texts):
            columns = _header_columns(pairs)
            continue
        if any("合计" in text for text in texts):
            if columns is not None and "amount" in columns:
                current.excel_total_amount = money_from_excel(
                    sheet.cell_value(row_index, columns["amount"])
                )
            _check_order_total(current, warnings)
            _flush(current, orders, warnings)
            current = None
            columns = None
            continue
        if columns is None:
            _apply_meta(current, pairs, biz_date, span_end, conflicts)
            continue
        line = _read_line(sheet, row_index, columns)
        if line is not None:
            current.lines.append(line)

    _flush(current, orders, warnings)
    if not orders:
        warnings.append(ParseWarning(code="EMPTY_FILE", message=f"{path.name} 没有识别到订单"))
    return ParsedShipment(
        sheet_name=sheet.name,
        orders=orders,
        conflicts=list(conflicts.values()),
        warnings=warnings,
    )


def _flush(current: ParsedOrder | None, orders: list[ParsedOrder], warnings: list[ParseWarning]) -> None:
    if current is None:
        return
    if current.customer_raw_name.strip() == "":
        if current.lines:
            warnings.append(ParseWarning(code="ORDER_WITHOUT_CUSTOMER", message="有商品明细但没有客户名称，已跳过"))
        return
    orders.append(current)


def _check_order_total(order: ParsedOrder, warnings: list[ParseWarning]) -> None:
    if order.excel_total_amount is None or order.customer_raw_name.strip() == "":
        return
    computed = sum_money([line.amount for line in order.lines if line.amount is not None])
    # 差在 5 分以内多半是原表合计的舍入，不单独提示。更大的差额留在导入提示里。
    if abs(computed - order.excel_total_amount) > Decimal("0.05"):
        warnings.append(
            ParseWarning(
                code="ORDER_TOTAL_MISMATCH",
                message=(
                    f"{order.customer_raw_name} 合计不一致："
                    f"表内 {order.excel_total_amount}，明细合计 {computed}"
                ),
            )
        )


def _apply_meta(
    order: ParsedOrder,
    pairs: list[tuple[int, str]],
    biz_date: date,
    span_end: date,
    conflicts: dict[date, ParsedConflict],
) -> None:
    fields = _extract_fields(pairs)
    if "市场名称" in fields and order.market_name is None:
        order.market_name = _blank_none(fields["市场名称"])
    if "电话" in fields and order.phone is None:
        order.phone = _blank_none(fields["电话"])
    if "详细地址" in fields and order.address is None:
        order.address = _blank_none(fields["详细地址"])
    if "价格比率" in fields and order.price_ratio is None:
        order.price_ratio = _blank_none(fields["价格比率"])
    if "客户名称" in fields and order.customer_raw_name == "":
        order.customer_raw_name = fields["客户名称"].strip()
    if "发货日期" in fields and order.ship_date_text is None:
        order.ship_date_text = _blank_none(fields["发货日期"])
        _record_conflict(order.ship_date_text, biz_date, span_end, conflicts)


def _record_conflict(
    cell_text_value: str | None,
    biz_date: date,
    span_end: date,
    conflicts: dict[date, ParsedConflict],
) -> None:
    if not cell_text_value:
        return
    parsed = _cell_start_date(cell_text_value)
    # 15-16 这类跨日文件里，单元格写成区间内的另一天不算冲突。月份对不上才列出。
    if parsed is None or biz_date <= parsed <= span_end or parsed in conflicts:
        return
    conflicts[parsed] = ParsedConflict(
        cell_text=cell_text_value,
        parsed_cell_date=parsed,
        biz_date=biz_date,
    )


def _cell_start_date(text: str) -> date | None:
    matched = _CELL_DATE.search(text)
    if matched is None:
        return None
    try:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
    except ValueError:
        return None


def _extract_fields(pairs: list[tuple[int, str]]) -> dict[str, str]:
    found: dict[str, str] = {}
    for index, (_col, text) in enumerate(pairs):
        for label in _LABELS:
            if label not in text:
                continue
            after = ""
            for separator in ("：", ":"):
                if separator in text:
                    after = text.split(separator, 1)[1].strip()
                    break
            if after:
                found[label] = after
            elif index + 1 < len(pairs) and not _looks_like_label(pairs[index + 1][1]):
                found[label] = pairs[index + 1][1]
    return found


def _looks_like_label(text: str) -> bool:
    return any(label in text for label in _LABELS)


def _header_columns(pairs: list[tuple[int, str]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    gift_seen = 0
    for col, text in pairs:
        if "产品名称" in text:
            mapping["product"] = col
        elif text == "单位":
            mapping["unit"] = col
        elif "订单数量" in text:
            mapping["order_qty"] = col
        elif "发货数量" in text:
            mapping["ship_qty"] = col
        elif "重量合计" in text:
            mapping["weight_total"] = col
        elif "实发重量" in text:
            mapping["actual_weight"] = col
        elif "实发数量" in text:
            mapping["actual_qty"] = col
        elif text == "单价":
            mapping["price"] = col
        elif text == "金额":
            mapping["amount"] = col
        elif "赠品" in text:
            gift_seen += 1
            mapping["gift_qty" if gift_seen == 1 else "gift_weight"] = col
    return mapping


def _read_line(sheet: Sheet, row_index: int, columns: dict[str, int]) -> ParsedLine | None:
    product_col = columns.get("product")
    if product_col is None:
        return None
    product_name = _product_name(sheet, row_index, product_col)
    if product_name == "" or "产品名称" in product_name or "合计" in product_name:
        return None
    return ParsedLine(
        product_name=product_name,
        unit=_optional_text(sheet, row_index, columns.get("unit")),
        order_qty=_optional_qty(sheet, row_index, columns.get("order_qty")),
        ship_qty=_optional_qty(sheet, row_index, columns.get("ship_qty")),
        gift_qty=_optional_qty(sheet, row_index, columns.get("gift_qty")),
        weight_total=_optional_qty(sheet, row_index, columns.get("weight_total")),
        actual_weight=_optional_qty(sheet, row_index, columns.get("actual_weight")),
        gift_weight=_optional_qty(sheet, row_index, columns.get("gift_weight")),
        actual_qty=_optional_qty(sheet, row_index, columns.get("actual_qty")),
        unit_price=_optional_qty(sheet, row_index, columns.get("price")),
        amount=_optional_money(sheet, row_index, columns.get("amount")),
    )


def _product_name(sheet: Sheet, row_index: int, product_col: int) -> str:
    # 表头在合并区右侧，品名写在左侧单元格。
    for col in (product_col - 1, product_col):
        if col < 0:
            continue
        text = cell_text(sheet.cell_value(row_index, col))
        if text and "产品名称" not in text:
            return text
    return ""


def _optional_text(sheet: Sheet, row_index: int, col: int | None) -> str | None:
    if col is None:
        return None
    return _blank_none(cell_text(sheet.cell_value(row_index, col)))


def _optional_qty(sheet: Sheet, row_index: int, col: int | None) -> Decimal | None:
    if col is None:
        return None
    return qty_from_excel(sheet.cell_value(row_index, col))


def _optional_money(sheet: Sheet, row_index: int, col: int | None) -> Decimal | None:
    if col is None:
        return None
    return money_from_excel(sheet.cell_value(row_index, col))


def _nonempty_texts(sheet: Sheet, row_index: int) -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    for col in range(sheet.ncols):
        text = cell_text(sheet.cell_value(row_index, col))
        if text:
            pairs.append((col, text))
    return pairs


def _blank_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
