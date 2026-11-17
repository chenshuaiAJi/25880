from dataclasses import dataclass, field
import logging
import threading
from pathlib import Path
from typing import Literal

from psycopg_pool import ConnectionPool

from app.importer.filenames import (
    detect_year,
    list_workbooks,
    parse_month_dir,
    parse_remittance_filename,
    parse_shipment_filename,
    shipment_span_end,
)
from app.importer.persist import persist_remittance, persist_shipment, relative_posix
from app.importer.remittance_parser import parse_remittance_workbook
from app.importer.shipment_parser import parse_shipment_workbook

logger = logging.getLogger(__name__)
ImportMode = Literal["skip", "replace"]
ImportKind = Literal["remittance", "shipment"]


class ImportBusy(Exception):
    pass


@dataclass
class ImportFailure:
    file: str
    message: str


@dataclass
class ImportSummary:
    shipmentFiles: int = 0
    remittanceFiles: int = 0
    skippedFiles: int = 0
    failedFiles: int = 0
    orders: int = 0
    lines: int = 0
    storesCreated: int = 0
    conflicts: int = 0
    warnings: int = 0
    ignored: list[str] = field(default_factory=list)
    failures: list[ImportFailure] = field(default_factory=list)


@dataclass(frozen=True)
class UploadImportJob:
    kind: ImportKind
    path: Path
    year: int
    month: int | None = None


class ImportRunner:
    def __init__(self, pool: ConnectionPool, data_root: Path) -> None:
        self._pool = pool
        self._data_root = data_root
        self._lock = threading.Lock()
        self._status: Literal["idle", "running", "done", "error"] = "idle"
        self._files_done = 0
        self._files_total = 0
        self._current_file = ""
        self._summary = ImportSummary()
        self._error = ""

    def start(self, mode: ImportMode) -> None:
        self._begin(mode)
        thread = threading.Thread(target=self._run_directory, args=(mode,), name="import-excel", daemon=True)
        thread.start()

    def start_uploads(self, mode: ImportMode, jobs: list[UploadImportJob]) -> None:
        if not jobs:
            raise ValueError("请至少选择一个 Excel 文件")
        self._begin(mode)
        thread = threading.Thread(
            target=self._run_uploads,
            args=(mode, jobs),
            name="import-upload",
            daemon=True,
        )
        thread.start()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            summary = self._summary
            return {
                "status": self._status,
                "filesDone": self._files_done,
                "filesTotal": self._files_total,
                "currentFile": self._current_file,
                "error": self._error or None,
                "result": {
                    "shipmentFiles": summary.shipmentFiles,
                    "remittanceFiles": summary.remittanceFiles,
                    "skippedFiles": summary.skippedFiles,
                    "failedFiles": summary.failedFiles,
                    "orders": summary.orders,
                    "lines": summary.lines,
                    "storesCreated": summary.storesCreated,
                    "conflicts": summary.conflicts,
                    "warnings": summary.warnings,
                    "ignored": list(summary.ignored),
                    "failures": [{"file": item.file, "message": item.message} for item in summary.failures],
                },
            }

    def _begin(self, mode: ImportMode) -> None:
        with self._lock:
            if self._status == "running":
                raise ImportBusy()
            self._status = "running"
            self._files_done = 0
            self._files_total = 0
            self._current_file = ""
            self._summary = ImportSummary()
            self._error = ""
            _ = mode

    def _run_directory(self, mode: ImportMode) -> None:
        try:
            root = self._data_root
            if not root.is_dir():
                raise FileNotFoundError(f"资料目录不存在：{root}")
            year = detect_year(root)
            listed = list_workbooks(root)
            files = [("remittance", path) for path in listed.remittances] + [
                ("shipment", path) for path in listed.shipments
            ]
            with self._lock:
                self._files_total = len(files)
                self._summary.ignored = list(listed.ignored)
            logger.info(
                "开始目录导入",
                extra={"fields": {"files": len(files), "ignored": len(listed.ignored), "mode": mode, "year": year}},
            )
            for index, (kind, path) in enumerate(files, start=1):
                self._import_one(kind, path, year, mode, month=None)
                with self._lock:
                    self._files_done = index
                if index % 50 == 0:
                    logger.info("导入进度", extra={"fields": {"filesDone": index, "filesTotal": len(files)}})
            self._finish_ok()
        except Exception as error:
            self._finish_error(error)

    def _run_uploads(self, mode: ImportMode, jobs: list[UploadImportJob]) -> None:
        try:
            with self._lock:
                self._files_total = len(jobs)
            logger.info(
                "开始上传导入",
                extra={"fields": {"files": len(jobs), "mode": mode}},
            )
            for index, job in enumerate(jobs, start=1):
                self._import_one(job.kind, job.path, job.year, mode, month=job.month)
                with self._lock:
                    self._files_done = index
            self._finish_ok()
        except Exception as error:
            self._finish_error(error)

    def _import_one(
        self,
        kind: ImportKind,
        path: Path,
        year: int,
        mode: ImportMode,
        *,
        month: int | None,
    ) -> None:
        root = self._data_root
        relative = relative_posix(path, root) if path.is_relative_to(root) else path.name
        with self._lock:
            self._current_file = relative
        try:
            if kind == "remittance":
                self._import_remittance(path, root, year, mode)
            else:
                self._import_shipment(path, root, year, mode, month=month)
        except Exception as error:
            logger.exception("导入文件失败", extra={"fields": {"file": relative}})
            with self._lock:
                self._summary.failedFiles += 1
                self._summary.failures.append(ImportFailure(relative, str(error)))

    def _finish_ok(self) -> None:
        with self._lock:
            self._status = "done"
            self._current_file = ""
            summary = self._summary
        logger.info(
            "导入完成",
            extra={
                "fields": {
                    "shipmentFiles": summary.shipmentFiles,
                    "remittanceFiles": summary.remittanceFiles,
                    "skippedFiles": summary.skippedFiles,
                    "failedFiles": summary.failedFiles,
                    "orders": summary.orders,
                    "storesCreated": summary.storesCreated,
                    "conflicts": summary.conflicts,
                }
            },
        )

    def _finish_error(self, error: Exception) -> None:
        logger.exception("导入中断")
        with self._lock:
            self._status = "error"
            self._error = str(error)

    def _import_remittance(self, path: Path, root: Path, year: int, mode: ImportMode) -> None:
        file_year, month = parse_remittance_filename(path.name, year)
        parsed = parse_remittance_workbook(path)
        relative = relative_posix(path, root) if path.is_relative_to(root) else f"新汇款明细/{path.name}"
        with self._pool.connection() as conn:
            with conn.transaction():
                status, created = persist_remittance(
                    conn,
                    relative,
                    path.name,
                    file_year,
                    month,
                    parsed,
                    mode,
                )
        with self._lock:
            if status == "skipped":
                self._summary.skippedFiles += 1
            else:
                self._summary.remittanceFiles += 1
                self._summary.storesCreated += created
                self._summary.warnings += len(parsed.warnings)

    def _import_shipment(
        self,
        path: Path,
        root: Path,
        year: int,
        mode: ImportMode,
        *,
        month: int | None,
    ) -> None:
        resolved_month = month if month is not None else parse_month_dir(path.parent.name)
        location = parse_shipment_filename(path.name, year, resolved_month)
        parsed = parse_shipment_workbook(path, location.biz_date, shipment_span_end(location))
        relative = (
            relative_posix(path, root)
            if path.is_relative_to(root)
            else f"发货单/{resolved_month}月份/{path.name}"
        )
        with self._pool.connection() as conn:
            with conn.transaction():
                status, created, orders, lines = persist_shipment(
                    conn,
                    relative,
                    location.year,
                    location.month,
                    location.batch_no,
                    location.batch_label,
                    location.biz_date,
                    path.name,
                    parsed,
                    mode,
                )
        with self._lock:
            if status == "skipped":
                self._summary.skippedFiles += 1
            else:
                self._summary.shipmentFiles += 1
                self._summary.storesCreated += created
                self._summary.orders += orders
                self._summary.lines += lines
                self._summary.conflicts += len(parsed.conflicts)
                self._summary.warnings += len(parsed.warnings)
