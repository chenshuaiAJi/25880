import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_SHIPMENT_FILE = re.compile(
    r"^(\d{1,2})\s*-\s*\+?(\d{1,2})(?:\s*\((\d+)\)|([A-Za-z]))?\.xls$",
    re.IGNORECASE,
)
_MONTH_DIR = re.compile(r"^(\d{1,2})月份$")
_REMITTANCE_FILE = re.compile(r"^(\d{1,2})月.*\.xls$", re.IGNORECASE)
_YEAR = re.compile(r"(\d{4})年")


@dataclass(frozen=True)
class ShipmentLocation:
    year: int
    month: int
    start_day: int
    end_day: int
    batch_no: int
    batch_label: str
    biz_date: date
    file_name: str


def detect_year(path: Path) -> int:
    for part in reversed(path.parts):
        matched = _YEAR.search(part)
        if matched is not None:
            return int(matched.group(1))
    raise ValueError(f"路径里没有年份：{path}")


def parse_shipment_filename(file_name: str, year: int, month: int) -> ShipmentLocation:
    matched = _SHIPMENT_FILE.match(file_name)
    if matched is None:
        raise ValueError(f"发货单文件名无法识别：{file_name}")
    start_day = int(matched.group(1))
    end_day = int(matched.group(2))
    if matched.group(3):
        batch_no = int(matched.group(3))
        batch_label = f"({batch_no})"
    elif matched.group(4):
        letter = matched.group(4).upper()
        batch_no = 100 + ord(letter) - ord("A") + 1
        batch_label = letter
    else:
        batch_no = 0
        batch_label = ""
    try:
        biz_date = date(year, month, start_day)
    except ValueError as error:
        raise ValueError(f"{year}年{month}月没有{start_day}日：{file_name}") from error
    return ShipmentLocation(
        year=year,
        month=month,
        start_day=start_day,
        end_day=end_day,
        batch_no=batch_no,
        batch_label=batch_label,
        biz_date=biz_date,
        file_name=file_name,
    )


def shipment_span_end(location: ShipmentLocation) -> date:
    """文件名 15-16 覆盖起始日到结束日；31-1 结束日落到下一个月。"""
    try:
        if location.end_day >= location.start_day:
            return date(location.year, location.month, location.end_day)
        if location.month == 12:
            return date(location.year + 1, 1, location.end_day)
        return date(location.year, location.month + 1, location.end_day)
    except ValueError:
        return location.biz_date


def parse_month_dir(name: str) -> int:
    matched = _MONTH_DIR.match(name)
    if matched is None:
        raise ValueError(f"不是月份目录：{name}")
    month = int(matched.group(1))
    if month < 1 or month > 12:
        raise ValueError(f"月份超出范围：{name}")
    return month


def parse_remittance_filename(file_name: str, year: int) -> tuple[int, int]:
    matched = _REMITTANCE_FILE.match(file_name)
    if matched is None:
        raise ValueError(f"汇款文件名无法识别：{file_name}")
    month = int(matched.group(1))
    if month < 1 or month > 12:
        raise ValueError(f"汇款月份超出范围：{file_name}")
    return year, month


@dataclass(frozen=True)
class WorkbookList:
    shipments: tuple[Path, ...]
    remittances: tuple[Path, ...]
    ignored: tuple[str, ...]


def list_workbooks(root: Path) -> WorkbookList:
    """只收集 .xls。exe、快捷方式、无扩展名文件放进 ignored，不进业务库。"""
    shipments: list[Path] = []
    remittances: list[Path] = []
    ignored: list[str] = []
    shipment_root = root / "发货单"
    remittance_root = root / "新汇款明细"
    if shipment_root.is_dir():
        for month_dir in sorted(shipment_root.iterdir(), key=lambda item: item.name):
            if not month_dir.is_dir():
                ignored.append(month_dir.relative_to(root).as_posix())
                continue
            if _MONTH_DIR.match(month_dir.name) is None:
                ignored.append(month_dir.relative_to(root).as_posix())
                continue
            for entry in sorted(month_dir.iterdir(), key=lambda item: item.name):
                if _is_workbook(entry):
                    shipments.append(entry)
                elif entry.is_file():
                    ignored.append(entry.relative_to(root).as_posix())
    if remittance_root.is_dir():
        for entry in sorted(remittance_root.iterdir(), key=lambda item: item.name):
            if _is_workbook(entry):
                remittances.append(entry)
            elif entry.is_file():
                ignored.append(entry.relative_to(root).as_posix())
    return WorkbookList(tuple(shipments), tuple(remittances), tuple(ignored))


def _is_workbook(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".xls" and not path.name.startswith("~$")
