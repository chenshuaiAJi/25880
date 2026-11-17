import {
  isRecord,
  readNullableString,
  readNumber,
  readString,
  readStringArray,
  requestJson,
} from "@/api/http"

export interface DayAmount {
  remit: string | null
  ship: string | null
}

export interface RemittanceMonth {
  year: number
  month: number
  dayCount: number
}

export interface RemittanceRow {
  id: number
  storeId: number
  displayName: string
  importedRawName: string
  openingBalance: string
  remitTotal: string
  shipTotal: string
  balance: string
  cells: Record<string, DayAmount>
}

export interface NextMonthPreview {
  sourceYear: number
  sourceMonth: number
  targetYear: number
  targetMonth: number
  targetDayCount: number
  canCreate: boolean
  blockers: string[]
  message: string
  storeCount: number
  openingGaps: OpeningMismatch[]
}

export interface OpeningMismatch {
  storeId: number
  displayName: string
  previousBalance: string
  currentOpening: string
  difference: string
}

export interface MergePreview {
  keepStore: StoreSummary
  mergeStore: StoreSummary
  orderCount: number
  remittanceRowCount: number
  overlaps: MergeOverlap[]
}

export interface MergeOverlap {
  year: number
  month: number
  keepOpening: string
  mergeOpening: string
  sumOpening: string
  days: Array<{
    day: number
    kind: string
    keepAmount: string
    mergeAmount: string
    sumAmount: string
  }>
}

export interface RemittanceSheet {
  year: number
  month: number
  dayCount: number
  calendarDays: number
  rows: RemittanceRow[]
}

export interface ShipmentMonth {
  year: number
  month: number
  orderCount: number
}

export interface ShipmentListItem {
  id: number
  bizDate: string
  customerRawName: string
  storeId: number
  displayName: string
  fileName: string
  batchNo: number
  batchLabel: string
  year: number
  month: number
  totalAmount: string
  lineCount: number
}

export interface ShipmentPage {
  page: number
  pageSize: number
  total: number
  items: ShipmentListItem[]
}

export interface ShipmentLine {
  lineIndex: number
  productName: string
  unit: string | null
  orderQty: string | null
  shipQty: string | null
  giftQty: string | null
  weightTotal: string | null
  actualWeight: string | null
  giftWeight: string | null
  actualQty: string | null
  unitPrice: string | null
  amount: string | null
}

export interface ShipmentDetail {
  id: number
  bizDate: string
  customerRawName: string
  displayName: string
  storeId: number
  marketName: string | null
  phone: string | null
  address: string | null
  priceRatio: string | null
  shipDateText: string | null
  fileName: string
  relativePath: string
  batchNo: number
  batchLabel: string
  year: number
  month: number
  totalAmount: string
  lines: ShipmentLine[]
}

export interface StoreSummary {
  id: number
  displayName: string
  code: string | null
  managerName: string | null
  phone: string | null
  address: string | null
  orderCount: number
  remittanceRowCount: number
}

export interface StoreAlias {
  rawName: string
  source: string
  documentCount: number
}

export interface StoreDetail extends StoreSummary {
  aliases: StoreAlias[]
}

export interface LedgerStats {
  stores: number
  orders: number
  lines: number
  sheets: number
  conflicts: number
  warnings: number
}

export interface ImportFailure {
  file: string
  message: string
}

export interface ImportResult {
  shipmentFiles: number
  remittanceFiles: number
  skippedFiles: number
  failedFiles: number
  orders: number
  lines: number
  storesCreated: number
  conflicts: number
  warnings: number
  ignored: string[]
  failures: ImportFailure[]
}

export interface ImportStatus {
  status: string
  filesDone: number
  filesTotal: number
  currentFile: string
  error: string | null
  result: ImportResult
}

export interface ConflictItem {
  id: number
  cellText: string
  parsedCellDate: string | null
  bizDate: string
  fileName: string
  relativePath: string
  year: number
  month: number
  batchNo: number
  batchLabel: string
}

export interface WarningItem {
  id: number
  code: string
  message: string
  fileName: string | null
  relativePath: string | null
}

export interface SystemInfo {
  version: string
  dataRoot: string
}

export interface ShipmentQuery {
  year?: number
  month?: number
  dateFrom?: string
  dateTo?: string
  batchNo?: number
  storeId?: number
  keyword?: string
  page: number
  pageSize: number
}

export async function fetchRemittanceMonths(): Promise<RemittanceMonth[]> {
  return parseRemittanceMonths(await requestJson("/api/remittances/months"))
}

export async function fetchRemittanceSheet(year: number, month: number): Promise<RemittanceSheet> {
  return parseRemittanceSheet(await requestJson(`/api/remittances/${year}/${month}`))
}

export interface BankTransaction {
  id: number
  txnDate: string
  txnTime: string | null
  amount: string
  direction: string
  counterpartyName: string | null
  purpose: string | null
  memo: string | null
  matchStatus: string
  matchedDate: string | null
  storeId: number | null
  displayName: string | null
}

export interface BankTxnPage {
  page: number
  pageSize: number
  total: number
  items: BankTransaction[]
}

export interface BankGap {
  storeId: number
  displayName: string
  date: string
  bankTotal: string
  remitAmount: string | null
  difference: string
}

export async function downloadRemittanceExport(year: number, month: number): Promise<void> {
  let response: Response
  try {
    response = await fetch(`/api/remittances/${year}/${month}/export`)
  } catch {
    throw new Error("无法连接对账服务，请确认 http://127.0.0.1:8787 已启动")
  }
  if (!response.ok) {
    let message = "导出失败"
    try {
      const body: unknown = await response.json()
      if (isRecord(body) && isRecord(body.error) && typeof body.error.message === "string") {
        message = body.error.message
      }
    } catch {
      // 非 JSON 错误体时用默认文案
    }
    throw new Error(message)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filenameFromDisposition(response.headers.get("Content-Disposition"), year, month)
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function filenameFromDisposition(header: string | null, year: number, month: number): string {
  const fallback = `汇款月表-${year}年${month}月.xlsx`
  if (header === null) {
    return fallback
  }
  const matched = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(header)
  if (matched === null) {
    return fallback
  }
  const raw = matched[1] ?? matched[2]
  if (raw === undefined || raw === "") {
    return fallback
  }
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

export async function fetchShipmentMonths(): Promise<ShipmentMonth[]> {
  return parseShipmentMonths(await requestJson("/api/shipments/months"))
}

export async function fetchShipments(query: ShipmentQuery): Promise<ShipmentPage> {
  return parseShipmentPage(await requestJson(`/api/shipments?${toQuery(query)}`))
}

export async function fetchShipment(id: number): Promise<ShipmentDetail> {
  return parseShipmentDetail(await requestJson(`/api/shipments/${id}`))
}

export async function fetchStores(keyword: string): Promise<StoreSummary[]> {
  const path = keyword.trim() === "" ? "/api/stores" : `/api/stores?keyword=${encodeURIComponent(keyword.trim())}`
  return parseStores(await requestJson(path))
}

export async function fetchStore(id: number): Promise<StoreDetail> {
  return parseStoreDetail(await requestJson(`/api/stores/${id}`))
}

export async function fetchStats(): Promise<LedgerStats> {
  return parseStats(await requestJson("/api/stats"))
}

export async function fetchSystem(): Promise<SystemInfo> {
  return parseSystem(await requestJson("/api/system"))
}

export async function startImport(mode: "skip" | "replace"): Promise<ImportStatus> {
  return parseImportStatus(await requestJson(`/api/imports?mode=${mode}`, { method: "POST" }))
}

export async function uploadImportFiles(payload: {
  kind: "remittance" | "shipment"
  year: number
  month?: number
  mode: "skip" | "replace"
  files: File[]
}): Promise<ImportStatus> {
  if (payload.files.length === 0) {
    throw new Error("请选择要导入的 Excel 文件")
  }
  const form = new FormData()
  for (const file of payload.files) {
    form.append("files", file)
  }
  const params = new URLSearchParams()
  params.set("kind", payload.kind)
  params.set("year", String(payload.year))
  params.set("mode", payload.mode)
  if (payload.kind === "shipment") {
    if (payload.month === undefined) {
      throw new Error("导入发货单时请选择月份")
    }
    params.set("month", String(payload.month))
  }
  return parseImportStatus(
    await requestJson(`/api/imports/upload?${params.toString()}`, {
      method: "POST",
      body: form,
    }),
  )
}

export async function fetchImportStatus(): Promise<ImportStatus> {
  return parseImportStatus(await requestJson("/api/imports/status"))
}

export async function fetchConflicts(page: number, pageSize: number): Promise<{ total: number; items: ConflictItem[] }> {
  const body = await requestJson(`/api/imports/conflicts?page=${page}&pageSize=${pageSize}`)
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error("日期冲突响应格式不正确")
  }
  return { total: readNumber(body, "total"), items: body.items.map(parseConflict) }
}

export async function fetchWarnings(page: number, pageSize: number): Promise<{ total: number; items: WarningItem[] }> {
  const body = await requestJson(`/api/imports/warnings?page=${page}&pageSize=${pageSize}`)
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error("导入提示响应格式不正确")
  }
  return { total: readNumber(body, "total"), items: body.items.map(parseWarning) }
}

export async function patchRemittanceOpening(rowId: number, openingBalance: string): Promise<RemittanceSheet> {
  return parseRemittanceSheet(
    await requestJson(`/api/remittances/rows/${rowId}/opening`, {
      method: "PATCH",
      body: JSON.stringify({ openingBalance }),
    }),
  )
}

export async function patchRemittanceCell(
  rowId: number,
  day: number,
  kind: "remit" | "ship",
  amount: string | null,
): Promise<RemittanceSheet> {
  return parseRemittanceSheet(
    await requestJson(`/api/remittances/rows/${rowId}/cells`, {
      method: "PATCH",
      body: JSON.stringify({ day, kind, amount }),
    }),
  )
}

export async function reassignRemittanceRow(
  rowId: number,
  storeId: number,
  mode: "one" | "all",
): Promise<RemittanceSheet> {
  return parseRemittanceSheet(
    await requestJson(`/api/remittances/rows/${rowId}/reassign`, {
      method: "POST",
      body: JSON.stringify({ storeId, mode }),
    }),
  )
}

export async function addRemittanceRow(
  year: number,
  month: number,
  payload: {
    storeId?: number
    displayName?: string
    openingBalance?: string
  },
): Promise<RemittanceSheet> {
  return parseRemittanceSheet(
    await requestJson(`/api/remittances/${year}/${month}/rows`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  )
}

export async function fetchNextMonthPreview(year: number, month: number): Promise<NextMonthPreview> {
  return parseNextMonthPreview(await requestJson(`/api/remittances/${year}/${month}/next-preview`))
}

export async function createNextMonthSheet(
  year: number,
  month: number,
  continueWithGaps: boolean,
): Promise<{ sheet: RemittanceSheet }> {
  const body = await requestJson(`/api/remittances/${year}/${month}/next`, {
    method: "POST",
    body: JSON.stringify({ continueWithGaps }),
  })
  if (!isRecord(body)) {
    throw new Error("创建下月响应格式不正确")
  }
  return { sheet: parseRemittanceSheet(body.sheet) }
}

export async function fetchOpeningMismatches(year: number, month: number): Promise<OpeningMismatch[]> {
  const body = await requestJson(`/api/remittances/${year}/${month}/opening-mismatches`)
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error("期初不平响应格式不正确")
  }
  return body.items.map(parseOpeningMismatch)
}

export async function applyOpeningBalances(year: number, month: number, storeIds: number[] | null): Promise<RemittanceSheet> {
  const body = await requestJson(`/api/remittances/${year}/${month}/apply-opening`, {
    method: "POST",
    body: JSON.stringify({ storeIds }),
  })
  if (!isRecord(body)) {
    throw new Error("覆盖期初响应格式不正确")
  }
  return parseRemittanceSheet(body.sheet)
}

export async function patchShipmentLine(
  orderId: number,
  lineIndex: number,
  payload: { shipQty?: string; unitPrice?: string; amount?: string; edited: "qty" | "price" | "amount" },
): Promise<ShipmentDetail> {
  return parseShipmentDetail(
    await requestJson(`/api/shipments/${orderId}/lines/${lineIndex}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  )
}

export async function reassignShipmentOrder(
  orderId: number,
  storeId: number,
  mode: "one" | "all",
): Promise<ShipmentDetail> {
  return parseShipmentDetail(
    await requestJson(`/api/shipments/${orderId}/reassign`, {
      method: "POST",
      body: JSON.stringify({ storeId, mode }),
    }),
  )
}

export async function patchStore(
  storeId: number,
  payload: {
    displayName?: string
    code?: string | null
    managerName?: string | null
    phone?: string | null
    address?: string | null
  },
): Promise<StoreDetail> {
  return parseStoreDetail(
    await requestJson(`/api/stores/${storeId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  )
}

export async function fetchMergePreview(keepStoreId: number, mergeStoreId: number): Promise<MergePreview> {
  return parseMergePreview(
    await requestJson(`/api/merges/preview?keepStoreId=${keepStoreId}&mergeStoreId=${mergeStoreId}`),
  )
}

export async function mergeStoreRecords(
  keepStoreId: number,
  mergeStoreId: number,
  displayName: string | null,
): Promise<StoreDetail> {
  return parseStoreDetail(
    await requestJson("/api/merges", {
      method: "POST",
      body: JSON.stringify({ keepStoreId, mergeStoreId, displayName }),
    }),
  )
}

export async function importBankFile(file: File): Promise<Record<string, unknown>> {
  const form = new FormData()
  form.append("file", file)
  const body = await requestJson("/api/bank/imports", {
    method: "POST",
    body: form,
  })
  if (!isRecord(body)) {
    throw new Error("银行导入响应格式不正确")
  }
  return body
}

export async function fetchBankTransactions(query: {
  direction?: string
  matchStatus?: string
  page: number
  pageSize: number
}): Promise<BankTxnPage> {
  const params = new URLSearchParams()
  params.set("page", String(query.page))
  params.set("pageSize", String(query.pageSize))
  if (query.direction) {
    params.set("direction", query.direction)
  }
  if (query.matchStatus) {
    params.set("matchStatus", query.matchStatus)
  }
  return parseBankPage(await requestJson(`/api/bank/transactions?${params.toString()}`))
}

export async function suggestBankMatches(): Promise<number> {
  const body = await requestJson("/api/bank/suggest", { method: "POST" })
  if (!isRecord(body)) {
    throw new Error("匹配建议响应格式不正确")
  }
  return readNumber(body, "suggested")
}

export async function assignBankTransaction(
  txnId: number,
  storeId: number,
  matchedDate: string,
  confirm: boolean,
): Promise<void> {
  await requestJson(`/api/bank/transactions/${txnId}/assign`, {
    method: "POST",
    body: JSON.stringify({ storeId, matchedDate, confirm }),
  })
}

export async function fetchBankGaps(year: number, month: number): Promise<BankGap[]> {
  const body = await requestJson(`/api/bank/remittance-gaps?year=${year}&month=${month}`)
  if (!isRecord(body) || !Array.isArray(body.items)) {
    throw new Error("汇款差额响应格式不正确")
  }
  return body.items.map((item) => {
    if (!isRecord(item)) {
      throw new Error("汇款差额项格式不正确")
    }
    return {
      storeId: readNumber(item, "storeId"),
      displayName: readString(item, "displayName"),
      date: readString(item, "date"),
      bankTotal: readString(item, "bankTotal"),
      remitAmount: readNullableString(item, "remitAmount"),
      difference: readString(item, "difference"),
    }
  })
}

export async function writebackBankRemittance(storeId: number, matchedDate: string): Promise<void> {
  await requestJson("/api/bank/writeback", {
    method: "POST",
    body: JSON.stringify({ storeId, matchedDate }),
  })
}

function parseBankPage(value: unknown): BankTxnPage {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new Error("银行流水列表格式不正确")
  }
  return {
    page: readNumber(value, "page"),
    pageSize: readNumber(value, "pageSize"),
    total: readNumber(value, "total"),
    items: value.items.map((item) => {
      if (!isRecord(item)) {
        throw new Error("银行流水格式不正确")
      }
      return {
        id: readNumber(item, "id"),
        txnDate: readString(item, "txnDate"),
        txnTime: readNullableString(item, "txnTime"),
        amount: readString(item, "amount"),
        direction: readString(item, "direction"),
        counterpartyName: readNullableString(item, "counterpartyName"),
        purpose: readNullableString(item, "purpose"),
        memo: readNullableString(item, "memo"),
        matchStatus: readString(item, "matchStatus"),
        matchedDate: readNullableString(item, "matchedDate"),
        storeId: typeof item.storeId === "number" ? item.storeId : null,
        displayName: readNullableString(item, "displayName"),
      }
    }),
  }
}

function toQuery(query: ShipmentQuery): string {
  const params = new URLSearchParams()
  params.set("page", String(query.page))
  params.set("pageSize", String(query.pageSize))
  append(params, "year", query.year)
  append(params, "month", query.month)
  append(params, "dateFrom", query.dateFrom)
  append(params, "dateTo", query.dateTo)
  append(params, "batchNo", query.batchNo)
  append(params, "storeId", query.storeId)
  if (query.keyword && query.keyword.trim() !== "") {
    params.set("keyword", query.keyword.trim())
  }
  return params.toString()
}

function append(params: URLSearchParams, key: string, value: string | number | undefined): void {
  if (value === undefined || value === "") {
    return
  }
  params.set(key, String(value))
}

function parseRemittanceMonths(value: unknown): RemittanceMonth[] {
  if (!Array.isArray(value)) {
    throw new Error("月份列表格式不正确")
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      throw new Error("月份列表格式不正确")
    }
    return { year: readNumber(item, "year"), month: readNumber(item, "month"), dayCount: readNumber(item, "dayCount") }
  })
}

function parseRemittanceSheet(value: unknown): RemittanceSheet {
  if (!isRecord(value) || !Array.isArray(value.rows)) {
    throw new Error("汇款月表格式不正确")
  }
  return {
    year: readNumber(value, "year"),
    month: readNumber(value, "month"),
    dayCount: readNumber(value, "dayCount"),
    calendarDays: readNumber(value, "calendarDays"),
    rows: value.rows.map(parseRemittanceRow),
  }
}

function parseRemittanceRow(value: unknown): RemittanceRow {
  if (!isRecord(value) || !isRecord(value.cells)) {
    throw new Error("汇款行格式不正确")
  }
  const cells: Record<string, DayAmount> = {}
  for (const [day, cell] of Object.entries(value.cells)) {
    if (!isRecord(cell)) {
      throw new Error("汇款单元格格式不正确")
    }
    cells[day] = { remit: readNullableString(cell, "remit"), ship: readNullableString(cell, "ship") }
  }
  return {
    id: readNumber(value, "id"),
    storeId: readNumber(value, "storeId"),
    displayName: readString(value, "displayName"),
    importedRawName: readString(value, "importedRawName"),
    openingBalance: readString(value, "openingBalance"),
    remitTotal: readString(value, "remitTotal"),
    shipTotal: readString(value, "shipTotal"),
    balance: readString(value, "balance"),
    cells,
  }
}

function parseNextMonthPreview(value: unknown): NextMonthPreview {
  if (!isRecord(value) || !Array.isArray(value.blockers) || !Array.isArray(value.openingGaps)) {
    throw new Error("下月预览格式不正确")
  }
  return {
    sourceYear: readNumber(value, "sourceYear"),
    sourceMonth: readNumber(value, "sourceMonth"),
    targetYear: readNumber(value, "targetYear"),
    targetMonth: readNumber(value, "targetMonth"),
    targetDayCount: readNumber(value, "targetDayCount"),
    canCreate: value.canCreate === true,
    blockers: value.blockers.filter((item): item is string => typeof item === "string"),
    message: readString(value, "message"),
    storeCount: readNumber(value, "storeCount"),
    openingGaps: value.openingGaps.map(parseOpeningMismatch),
  }
}

function parseOpeningMismatch(value: unknown): OpeningMismatch {
  if (!isRecord(value)) {
    throw new Error("期初不平格式不正确")
  }
  return {
    storeId: readNumber(value, "storeId"),
    displayName: readString(value, "displayName"),
    previousBalance: readString(value, "previousBalance"),
    currentOpening: readString(value, "currentOpening"),
    difference: readString(value, "difference"),
  }
}

function parseMergePreview(value: unknown): MergePreview {
  if (!isRecord(value) || !Array.isArray(value.overlaps)) {
    throw new Error("合并预览格式不正确")
  }
  return {
    keepStore: parseStoreSummary(value.keepStore),
    mergeStore: parseStoreSummary(value.mergeStore),
    orderCount: readNumber(value, "orderCount"),
    remittanceRowCount: readNumber(value, "remittanceRowCount"),
    overlaps: value.overlaps.map((item) => {
      if (!isRecord(item) || !Array.isArray(item.days)) {
        throw new Error("合并重叠格式不正确")
      }
      return {
        year: readNumber(item, "year"),
        month: readNumber(item, "month"),
        keepOpening: readString(item, "keepOpening"),
        mergeOpening: readString(item, "mergeOpening"),
        sumOpening: readString(item, "sumOpening"),
        days: item.days.map((day) => {
          if (!isRecord(day)) {
            throw new Error("合并日金额格式不正确")
          }
          return {
            day: readNumber(day, "day"),
            kind: readString(day, "kind"),
            keepAmount: readString(day, "keepAmount"),
            mergeAmount: readString(day, "mergeAmount"),
            sumAmount: readString(day, "sumAmount"),
          }
        }),
      }
    }),
  }
}

function parseShipmentMonths(value: unknown): ShipmentMonth[] {
  if (!Array.isArray(value)) {
    throw new Error("发货月份格式不正确")
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      throw new Error("发货月份格式不正确")
    }
    return { year: readNumber(item, "year"), month: readNumber(item, "month"), orderCount: readNumber(item, "orderCount") }
  })
}

function parseShipmentPage(value: unknown): ShipmentPage {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new Error("发货单列表格式不正确")
  }
  return {
    page: readNumber(value, "page"),
    pageSize: readNumber(value, "pageSize"),
    total: readNumber(value, "total"),
    items: value.items.map(parseShipmentItem),
  }
}

function parseShipmentBase(value: Record<string, unknown>): Omit<ShipmentListItem, "lineCount"> {
  return {
    id: readNumber(value, "id"),
    bizDate: readString(value, "bizDate"),
    customerRawName: readString(value, "customerRawName"),
    storeId: readNumber(value, "storeId"),
    displayName: readString(value, "displayName"),
    fileName: readString(value, "fileName"),
    batchNo: readNumber(value, "batchNo"),
    batchLabel: readString(value, "batchLabel"),
    year: readNumber(value, "year"),
    month: readNumber(value, "month"),
    totalAmount: readString(value, "totalAmount"),
  }
}

function parseShipmentItem(value: unknown): ShipmentListItem {
  if (!isRecord(value)) {
    throw new Error("发货单格式不正确")
  }
  return {
    ...parseShipmentBase(value),
    lineCount: readNumber(value, "lineCount"),
  }
}

function parseShipmentDetail(value: unknown): ShipmentDetail {
  if (!isRecord(value) || !Array.isArray(value.lines)) {
    throw new Error("发货明细格式不正确")
  }
  return {
    ...parseShipmentBase(value),
    marketName: readNullableString(value, "marketName"),
    phone: readNullableString(value, "phone"),
    address: readNullableString(value, "address"),
    priceRatio: readNullableString(value, "priceRatio"),
    shipDateText: readNullableString(value, "shipDateText"),
    relativePath: readString(value, "relativePath"),
    lines: value.lines.map(parseLine),
  }
}

function parseLine(value: unknown): ShipmentLine {
  if (!isRecord(value)) {
    throw new Error("商品行格式不正确")
  }
  return {
    lineIndex: readNumber(value, "lineIndex"),
    productName: readString(value, "productName"),
    unit: readNullableString(value, "unit"),
    orderQty: readNullableString(value, "orderQty"),
    shipQty: readNullableString(value, "shipQty"),
    giftQty: readNullableString(value, "giftQty"),
    weightTotal: readNullableString(value, "weightTotal"),
    actualWeight: readNullableString(value, "actualWeight"),
    giftWeight: readNullableString(value, "giftWeight"),
    actualQty: readNullableString(value, "actualQty"),
    unitPrice: readNullableString(value, "unitPrice"),
    amount: readNullableString(value, "amount"),
  }
}

function parseStores(value: unknown): StoreSummary[] {
  if (!Array.isArray(value)) {
    throw new Error("门店列表格式不正确")
  }
  return value.map(parseStoreSummary)
}

function parseStoreSummary(value: unknown): StoreSummary {
  if (!isRecord(value)) {
    throw new Error("门店格式不正确")
  }
  return {
    id: readNumber(value, "id"),
    displayName: readString(value, "displayName"),
    code: readNullableString(value, "code"),
    managerName: readNullableString(value, "managerName"),
    phone: readNullableString(value, "phone"),
    address: readNullableString(value, "address"),
    orderCount: readNumber(value, "orderCount"),
    remittanceRowCount: readNumber(value, "remittanceRowCount"),
  }
}

function parseStoreDetail(value: unknown): StoreDetail {
  if (!isRecord(value) || !Array.isArray(value.aliases)) {
    throw new Error("门店详情格式不正确")
  }
  return {
    ...parseStoreSummary(value),
    aliases: value.aliases.map((item) => {
      if (!isRecord(item)) {
        throw new Error("原始名称格式不正确")
      }
      return {
        rawName: readString(item, "rawName"),
        source: readString(item, "source"),
        documentCount: readNumber(item, "documentCount"),
      }
    }),
  }
}

function parseStats(value: unknown): LedgerStats {
  if (!isRecord(value)) {
    throw new Error("统计格式不正确")
  }
  return {
    stores: readNumber(value, "stores"),
    orders: readNumber(value, "orders"),
    lines: readNumber(value, "lines"),
    sheets: readNumber(value, "sheets"),
    conflicts: readNumber(value, "conflicts"),
    warnings: readNumber(value, "warnings"),
  }
}

function parseSystem(value: unknown): SystemInfo {
  if (!isRecord(value)) {
    throw new Error("系统信息格式不正确")
  }
  return { version: readString(value, "version"), dataRoot: readString(value, "dataRoot") }
}

function parseImportStatus(value: unknown): ImportStatus {
  if (!isRecord(value) || !isRecord(value.result)) {
    throw new Error("导入状态格式不正确")
  }
  const result = value.result
  return {
    status: readString(value, "status"),
    filesDone: readNumber(value, "filesDone"),
    filesTotal: readNumber(value, "filesTotal"),
    currentFile: readString(value, "currentFile"),
    error: readNullableString(value, "error"),
    result: {
      shipmentFiles: readNumber(result, "shipmentFiles"),
      remittanceFiles: readNumber(result, "remittanceFiles"),
      skippedFiles: readNumber(result, "skippedFiles"),
      failedFiles: readNumber(result, "failedFiles"),
      orders: readNumber(result, "orders"),
      lines: readNumber(result, "lines"),
      storesCreated: readNumber(result, "storesCreated"),
      conflicts: readNumber(result, "conflicts"),
      warnings: readNumber(result, "warnings"),
      ignored: readStringArray(result, "ignored"),
      failures: Array.isArray(result.failures) ? result.failures.map(parseFailure) : [],
    },
  }
}

function parseFailure(value: unknown): ImportFailure {
  if (!isRecord(value)) {
    throw new Error("失败记录格式不正确")
  }
  return { file: readString(value, "file"), message: readString(value, "message") }
}

function parseConflict(value: unknown): ConflictItem {
  if (!isRecord(value)) {
    throw new Error("日期冲突格式不正确")
  }
  return {
    id: readNumber(value, "id"),
    cellText: readString(value, "cellText"),
    parsedCellDate: readNullableString(value, "parsedCellDate"),
    bizDate: readString(value, "bizDate"),
    fileName: readString(value, "fileName"),
    relativePath: readString(value, "relativePath"),
    year: readNumber(value, "year"),
    month: readNumber(value, "month"),
    batchNo: readNumber(value, "batchNo"),
    batchLabel: readString(value, "batchLabel"),
  }
}

function parseWarning(value: unknown): WarningItem {
  if (!isRecord(value)) {
    throw new Error("导入提示格式不正确")
  }
  return {
    id: readNumber(value, "id"),
    code: readString(value, "code"),
    message: readString(value, "message"),
    fileName: readNullableString(value, "fileName"),
    relativePath: readNullableString(value, "relativePath"),
  }
}
