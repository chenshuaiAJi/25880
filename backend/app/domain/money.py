from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
QTY = Decimal("0.0001")


def decimal_from_excel(value: object, quantum: Decimal) -> Decimal | None:
    """按单元格数值读取。空单元格返回 None，显式 0 保留为 0。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if text == "" or set(text) == {"#"}:
            return None
        try:
            parsed = Decimal(text)
        except InvalidOperation:
            return None
        return parsed.quantize(quantum, rounding=ROUND_HALF_UP)
    if isinstance(value, int):
        return Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)
    if isinstance(value, float):
        return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return None


def money_from_excel(value: object) -> Decimal | None:
    return decimal_from_excel(value, MONEY)


def qty_from_excel(value: object) -> Decimal | None:
    return decimal_from_excel(value, QTY)


def money_text(value: Decimal) -> str:
    quantized = value.quantize(MONEY, rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def qty_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.quantize(QTY, rounding=ROUND_HALF_UP), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
