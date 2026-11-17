from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import APP_VERSION
from app.errors import AppError
from app.importer.runner import ImportBusy, ImportRunner, UploadImportJob
from app.readers.quality import ledger_stats, list_conflicts, list_warnings
from app.readers.remittances import get_remittance_sheet, list_remittance_months
from app.readers.shipments import get_shipment, list_shipment_months, search_shipments
from app.readers.stores import get_store, list_stores
from app.services.bank import (
    assign_bank_transaction,
    default_bank_root,
    import_bank_file,
    list_bank_transactions,
    remittance_gaps_for_matches,
    suggest_matches,
    writeback_remittance_from_bank,
)
from app.services.export_remittance import export_remittance_xlsx
from app.services.next_month import (
    apply_opening_from_previous,
    create_next_month,
    list_opening_mismatches,
    preview_create_next_month,
)
from app.services.remittances import (
    add_remittance_row,
    reassign_remittance_row,
    update_remittance_cell,
    update_remittance_opening,
)
from app.services.shipments import reassign_shipment_order, update_shipment_line
from app.services.stores import merge_stores, preview_merge_stores, update_store_profile

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str
    version: str


class SystemResponse(BaseModel):
    version: str
    dataRoot: str


class StatsResponse(BaseModel):
    stores: int
    orders: int
    lines: int
    sheets: int
    conflicts: int
    warnings: int


class MonthItem(BaseModel):
    year: int
    month: int
    dayCount: int


class ShipmentMonthItem(BaseModel):
    year: int
    month: int
    orderCount: int


class DayAmount(BaseModel):
    remit: str | None
    ship: str | None


class RemittanceRowModel(BaseModel):
    id: int
    storeId: int
    displayName: str
    importedRawName: str
    openingBalance: str
    remitTotal: str
    shipTotal: str
    balance: str
    cells: dict[str, DayAmount]


class RemittanceSheetModel(BaseModel):
    year: int
    month: int
    dayCount: int
    calendarDays: int
    rows: list[RemittanceRowModel]


class ShipmentListItem(BaseModel):
    id: int
    bizDate: str
    customerRawName: str
    storeId: int
    displayName: str
    fileName: str
    batchNo: int
    batchLabel: str
    year: int
    month: int
    totalAmount: str
    lineCount: int


class PageModel(BaseModel):
    page: int
    pageSize: int
    total: int
    items: list[ShipmentListItem]


class ShipmentLineModel(BaseModel):
    lineIndex: int
    productName: str
    unit: str | None
    orderQty: str | None
    shipQty: str | None
    giftQty: str | None
    weightTotal: str | None
    actualWeight: str | None
    giftWeight: str | None
    actualQty: str | None
    unitPrice: str | None
    amount: str | None


class ShipmentDetailModel(BaseModel):
    id: int
    bizDate: str
    customerRawName: str
    displayName: str
    storeId: int
    marketName: str | None
    phone: str | None
    address: str | None
    priceRatio: str | None
    shipDateText: str | None
    fileName: str
    relativePath: str
    batchNo: int
    batchLabel: str
    year: int
    month: int
    totalAmount: str
    lines: list[ShipmentLineModel]


class StoreModel(BaseModel):
    id: int
    displayName: str
    code: str | None
    managerName: str | None
    phone: str | None
    address: str | None
    orderCount: int
    remittanceRowCount: int


class StoreAliasModel(BaseModel):
    rawName: str
    source: str
    documentCount: int


class StoreDetailModel(StoreModel):
    aliases: list[StoreAliasModel]


class ConflictItem(BaseModel):
    id: int
    cellText: str
    parsedCellDate: str | None
    bizDate: str
    fileName: str
    relativePath: str
    year: int
    month: int
    batchNo: int
    batchLabel: str


class ConflictPage(BaseModel):
    page: int
    pageSize: int
    total: int
    items: list[ConflictItem]


class WarningItem(BaseModel):
    id: int
    code: str
    message: str
    fileName: str | None
    relativePath: str | None


class WarningPage(BaseModel):
    page: int
    pageSize: int
    total: int
    items: list[WarningItem]


class FailureItem(BaseModel):
    file: str
    message: str


class ImportResultModel(BaseModel):
    shipmentFiles: int
    remittanceFiles: int
    skippedFiles: int
    failedFiles: int
    orders: int
    lines: int
    storesCreated: int
    conflicts: int
    warnings: int
    ignored: list[str]
    failures: list[FailureItem]


class ImportStatusModel(BaseModel):
    status: str
    filesDone: int
    filesTotal: int
    currentFile: str
    error: str | None
    result: ImportResultModel


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    with request.app.state.pool.connection() as conn:
        conn.execute("SELECT 1")
    return HealthResponse(status="ok", version=APP_VERSION)


@router.get("/system", response_model=SystemResponse)
def system_info(request: Request) -> SystemResponse:
    return SystemResponse(version=APP_VERSION, dataRoot=str(request.app.state.settings.resolved_data_root()))


@router.get("/stats", response_model=StatsResponse)
def stats(request: Request) -> StatsResponse:
    with request.app.state.pool.connection() as conn:
        return StatsResponse.model_validate(ledger_stats(conn))


@router.get("/remittances/months", response_model=list[MonthItem])
def remittance_months(request: Request) -> list[MonthItem]:
    with request.app.state.pool.connection() as conn:
        return [MonthItem.model_validate(item) for item in list_remittance_months(conn)]


@router.get("/remittances/{year}/{month}", response_model=RemittanceSheetModel)
def remittance_sheet(
    year: int,
    month: int,
    request: Request,
) -> RemittanceSheetModel:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        sheet = get_remittance_sheet(conn, year, month)
    if sheet is None:
        raise AppError("这个月还没有汇款表", status_code=404, code="NOT_FOUND")
    return RemittanceSheetModel.model_validate(sheet)


@router.get("/shipments/months", response_model=list[ShipmentMonthItem])
def shipment_months(request: Request) -> list[ShipmentMonthItem]:
    with request.app.state.pool.connection() as conn:
        return [ShipmentMonthItem.model_validate(item) for item in list_shipment_months(conn)]


@router.get("/shipments", response_model=PageModel)
def shipment_list(
    request: Request,
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    batch_no: int | None = Query(default=None, alias="batchNo", ge=0, le=130),
    store_id: int | None = Query(default=None, alias="storeId", ge=1),
    keyword: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> PageModel:
    cleaned = keyword.strip() if keyword else None
    with request.app.state.pool.connection() as conn:
        payload = search_shipments(
            conn,
            year,
            month,
            date_from,
            date_to,
            batch_no,
            store_id,
            cleaned or None,
            page,
            page_size,
        )
    return PageModel.model_validate(payload)


@router.get("/shipments/{order_id}", response_model=ShipmentDetailModel)
def shipment_detail(order_id: int, request: Request) -> ShipmentDetailModel:
    with request.app.state.pool.connection() as conn:
        order = get_shipment(conn, order_id)
    if order is None:
        raise AppError("找不到这张发货单", status_code=404, code="NOT_FOUND")
    return ShipmentDetailModel.model_validate(order)


@router.get("/stores", response_model=list[StoreModel])
def stores(request: Request, keyword: str | None = Query(default=None, max_length=50)) -> list[StoreModel]:
    cleaned = keyword.strip() if keyword else None
    with request.app.state.pool.connection() as conn:
        rows = list_stores(conn, cleaned or None)
    return [StoreModel.model_validate(row) for row in rows]


@router.get("/stores/{store_id}", response_model=StoreDetailModel)
def store_detail(store_id: int, request: Request) -> StoreDetailModel:
    with request.app.state.pool.connection() as conn:
        store = get_store(conn, store_id)
    if store is None:
        raise AppError("找不到这家门店", status_code=404, code="NOT_FOUND")
    return StoreDetailModel.model_validate(store)


@router.post("/imports", response_model=ImportStatusModel)
def start_import(
    request: Request,
    mode: Literal["skip", "replace"] = Query(default="skip"),
) -> ImportStatusModel:
    runner: ImportRunner = request.app.state.importer
    try:
        runner.start(mode)
    except ImportBusy as error:
        raise AppError("正在导入，请等这次完成", status_code=409, code="BUSY") from error
    return ImportStatusModel.model_validate(runner.snapshot())


@router.post("/imports/upload", response_model=ImportStatusModel)
async def upload_import(
    request: Request,
    kind: Literal["remittance", "shipment"] = Query(...),
    year: int = Query(ge=2000, le=2100),
    mode: Literal["skip", "replace"] = Query(default="skip"),
    month: int | None = Query(default=None, ge=1, le=12),
    files: list[UploadFile] = File(...),
) -> ImportStatusModel:
    if kind == "shipment" and month is None:
        raise AppError("导入发货单时请选择月份")
    if not files:
        raise AppError("请选择要导入的 Excel 文件")
    root = request.app.state.settings.resolved_data_root()
    root.mkdir(parents=True, exist_ok=True)
    jobs: list[UploadImportJob] = []
    for upload in files:
        original = Path(upload.filename or "").name.strip()
        if original == "":
            raise AppError("存在没有文件名的上传项")
        suffix = Path(original).suffix.lower()
        if suffix != ".xls":
            raise AppError(f"只支持 .xls：{original}")
        if kind == "remittance":
            target_dir = root / "新汇款明细"
        else:
            assert month is not None
            target_dir = root / "发货单" / f"{month}月份"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / original).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as error:
            raise AppError(f"文件名不合法：{original}") from error
        content = await upload.read()
        if not content:
            raise AppError(f"上传文件是空的：{original}")
        target.write_bytes(content)
        jobs.append(UploadImportJob(kind=kind, path=target, year=year, month=month))
    runner: ImportRunner = request.app.state.importer
    try:
        runner.start_uploads(mode, jobs)
    except ImportBusy as error:
        raise AppError("正在导入，请等这次完成", status_code=409, code="BUSY") from error
    except ValueError as error:
        raise AppError(str(error)) from error
    return ImportStatusModel.model_validate(runner.snapshot())


@router.get("/imports/status", response_model=ImportStatusModel)
def import_status(request: Request) -> ImportStatusModel:
    runner: ImportRunner = request.app.state.importer
    return ImportStatusModel.model_validate(runner.snapshot())


@router.get("/imports/conflicts", response_model=ConflictPage)
def conflicts(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> ConflictPage:
    with request.app.state.pool.connection() as conn:
        return ConflictPage.model_validate(list_conflicts(conn, page, page_size))


@router.get("/imports/warnings", response_model=WarningPage)
def warnings(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> WarningPage:
    with request.app.state.pool.connection() as conn:
        return WarningPage.model_validate(list_warnings(conn, page, page_size))


class RemittanceOpeningBody(BaseModel):
    openingBalance: str = Field(min_length=1, max_length=32)


class RemittanceCellBody(BaseModel):
    day: int = Field(ge=1, le=31)
    kind: Literal["remit", "ship"]
    amount: str | None = Field(default=None, max_length=32)


class ReassignBody(BaseModel):
    storeId: int = Field(ge=1)
    mode: Literal["one", "all"] = "one"


class ShipmentLineBody(BaseModel):
    shipQty: str | None = Field(default=None, max_length=32)
    unitPrice: str | None = Field(default=None, max_length=32)
    amount: str | None = Field(default=None, max_length=32)
    edited: Literal["qty", "price", "amount"]


class StoreUpdateBody(BaseModel):
    displayName: str | None = Field(default=None, max_length=100)
    code: str | None = Field(default=None, max_length=50)
    managerName: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=200)


class MergeBody(BaseModel):
    keepStoreId: int = Field(ge=1)
    mergeStoreId: int = Field(ge=1)
    displayName: str | None = Field(default=None, max_length=100)


class CreateNextMonthBody(BaseModel):
    continueWithGaps: bool = False


class ApplyOpeningBody(BaseModel):
    storeIds: list[int] | None = None


class AddRemittanceRowBody(BaseModel):
    storeId: int | None = Field(default=None, ge=1)
    displayName: str | None = Field(default=None, max_length=100)
    openingBalance: str | None = Field(default=None, max_length=32)


@router.post("/remittances/{year}/{month}/rows", response_model=RemittanceSheetModel)
def post_add_remittance_row(
    year: int,
    month: int,
    body: AddRemittanceRowBody,
    request: Request,
) -> RemittanceSheetModel:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            sheet = add_remittance_row(
                conn,
                year,
                month,
                store_id=body.storeId,
                display_name=body.displayName,
                opening_balance=body.openingBalance,
            )
    return RemittanceSheetModel.model_validate(sheet)


@router.patch("/remittances/rows/{row_id}/opening", response_model=RemittanceSheetModel)
def patch_remittance_opening(row_id: int, body: RemittanceOpeningBody, request: Request) -> RemittanceSheetModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            sheet = update_remittance_opening(conn, row_id, body.openingBalance)
    return RemittanceSheetModel.model_validate(sheet)


@router.patch("/remittances/rows/{row_id}/cells", response_model=RemittanceSheetModel)
def patch_remittance_cell(row_id: int, body: RemittanceCellBody, request: Request) -> RemittanceSheetModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            sheet = update_remittance_cell(conn, row_id, body.day, body.kind, body.amount)
    return RemittanceSheetModel.model_validate(sheet)


@router.post("/remittances/rows/{row_id}/reassign", response_model=RemittanceSheetModel)
def post_reassign_remittance(row_id: int, body: ReassignBody, request: Request) -> RemittanceSheetModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            sheet = reassign_remittance_row(conn, row_id, body.storeId, body.mode)
    return RemittanceSheetModel.model_validate(sheet)


@router.get("/remittances/{year}/{month}/export")
def export_remittance_month(year: int, month: int, request: Request) -> Response:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        content, filename = export_remittance_xlsx(conn, year, month)
    encoded = quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


@router.get("/remittances/{year}/{month}/next-preview")
def next_month_preview(year: int, month: int, request: Request) -> dict[str, object]:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        return preview_create_next_month(conn, year, month)


@router.post("/remittances/{year}/{month}/next")
def next_month_create(year: int, month: int, body: CreateNextMonthBody, request: Request) -> dict[str, object]:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return create_next_month(conn, year, month, continue_with_gaps=body.continueWithGaps)


@router.get("/remittances/{year}/{month}/opening-mismatches")
def opening_mismatches(year: int, month: int, request: Request) -> dict[str, object]:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        return {"items": list_opening_mismatches(conn, year, month)}


@router.post("/remittances/{year}/{month}/apply-opening")
def apply_opening(year: int, month: int, body: ApplyOpeningBody, request: Request) -> dict[str, object]:
    _check_month(year, month)
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return apply_opening_from_previous(conn, year, month, body.storeIds)


@router.patch("/shipments/{order_id}/lines/{line_index}", response_model=ShipmentDetailModel)
def patch_shipment_line(
    order_id: int,
    line_index: int,
    body: ShipmentLineBody,
    request: Request,
) -> ShipmentDetailModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            order = update_shipment_line(
                conn,
                order_id,
                line_index,
                ship_qty=body.shipQty,
                unit_price=body.unitPrice,
                amount=body.amount,
                edited=body.edited,
            )
    return ShipmentDetailModel.model_validate(order)


@router.post("/shipments/{order_id}/reassign", response_model=ShipmentDetailModel)
def post_reassign_shipment(order_id: int, body: ReassignBody, request: Request) -> ShipmentDetailModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            order = reassign_shipment_order(conn, order_id, body.storeId, body.mode)
    return ShipmentDetailModel.model_validate(order)


@router.patch("/stores/{store_id}", response_model=StoreDetailModel)
def patch_store(store_id: int, body: StoreUpdateBody, request: Request) -> StoreDetailModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            store = update_store_profile(
                conn,
                store_id,
                display_name=body.displayName,
                code=body.code,
                manager_name=body.managerName,
                phone=body.phone,
                address=body.address,
            )
    return StoreDetailModel.model_validate(store)


@router.get("/merges/preview")
def store_merge_preview(
    request: Request,
    keep_store_id: int = Query(alias="keepStoreId", ge=1),
    merge_store_id: int = Query(alias="mergeStoreId", ge=1),
) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        return preview_merge_stores(conn, keep_store_id, merge_store_id)


@router.post("/merges", response_model=StoreDetailModel)
def store_merge(body: MergeBody, request: Request) -> StoreDetailModel:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            store = merge_stores(conn, body.keepStoreId, body.mergeStoreId, body.displayName)
    store.pop("mergePreview", None)
    return StoreDetailModel.model_validate(store)


class BankAssignBody(BaseModel):
    storeId: int = Field(ge=1)
    matchedDate: date
    confirm: bool = True


class BankWritebackBody(BaseModel):
    storeId: int = Field(ge=1)
    matchedDate: date


@router.post("/bank/imports")
async def bank_import(
    request: Request,
    file: UploadFile = File(..., description="银行下载的交易明细 Excel"),
) -> dict[str, object]:
    original_name = Path(file.filename or "").name.strip()
    if original_name == "":
        raise AppError("请选择要导入的银行明细文件")
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise AppError("只支持 .xlsx / .xls 银行明细")
    root = default_bank_root()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / original_name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise AppError("文件名不合法") from error
    content = await file.read()
    if not content:
        raise AppError("上传文件是空的")
    path.write_bytes(content)
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return import_bank_file(conn, path, root)


@router.get("/bank/transactions")
def bank_transactions(
    request: Request,
    direction: Literal["in", "out"] | None = Query(default=None),
    match_status: str | None = Query(default=None, alias="matchStatus"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, alias="pageSize", ge=1, le=200),
) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        return list_bank_transactions(
            conn,
            direction=direction,
            match_status=match_status,
            page=page,
            page_size=page_size,
        )


@router.post("/bank/suggest")
def bank_suggest(request: Request) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return {"suggested": suggest_matches(conn)}


@router.post("/bank/transactions/{txn_id}/assign")
def bank_assign(txn_id: int, body: BankAssignBody, request: Request) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return assign_bank_transaction(
                conn,
                txn_id,
                body.storeId,
                body.matchedDate,
                confirm=body.confirm,
            )


@router.get("/bank/remittance-gaps")
def bank_remittance_gaps(
    request: Request,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        return {"items": remittance_gaps_for_matches(conn, year, month)}


@router.post("/bank/writeback")
def bank_writeback(body: BankWritebackBody, request: Request) -> dict[str, object]:
    with request.app.state.pool.connection() as conn:
        with conn.transaction():
            return writeback_remittance_from_bank(conn, body.storeId, body.matchedDate)


def _check_month(year: int, month: int) -> None:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise AppError("年月不正确")
