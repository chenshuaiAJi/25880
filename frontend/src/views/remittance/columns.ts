import type { TableColumnData, TableData } from "@arco-design/web-vue/es/table/interface"
import { h, type VNode } from "vue"
import { isRecord } from "@/api/http"
import MoneyText from "@/components/MoneyText.vue"
import type { RemittanceRow } from "@/api/client"

export interface SheetRow {
  key: string
  rowId: number
  storeId: number
  displayName: string
  importedRawName: string
  amounts: Record<string, string | null>
}

export function toSheetRows(rows: RemittanceRow[]): SheetRow[] {
  return rows.map((row) => {
    const amounts: Record<string, string | null> = {
      openingBalance: row.openingBalance,
      remitTotal: row.remitTotal,
      shipTotal: row.shipTotal,
      balance: row.balance,
    }
    for (const [day, cell] of Object.entries(row.cells)) {
      amounts[`${day}r`] = cell.remit
      amounts[`${day}s`] = cell.ship
    }
    return {
      key: String(row.id),
      rowId: row.id,
      storeId: row.storeId,
      displayName: row.displayName,
      importedRawName: row.importedRawName,
      amounts,
    }
  })
}

export function buildColumns(dayCount: number, calendarDays: number): TableColumnData[] {
  const columns: TableColumnData[] = [
    {
      title: "门店",
      dataIndex: "displayName",
      width: 240,
      fixed: "left",
      ellipsis: true,
      tooltip: true,
    },
    moneyColumn("上月余额", "openingBalance", "left"),
  ]
  for (let day = 1; day <= dayCount; day += 1) {
    const mark = day > calendarDays ? "*" : ""
    columns.push(moneyColumn(`${day}日汇款${mark}`, `${day}r`))
    columns.push(moneyColumn(`${day}日发货${mark}`, `${day}s`))
  }
  columns.push(moneyColumn("汇款总额", "remitTotal", "right"))
  columns.push(moneyColumn("发货总额", "shipTotal", "right"))
  columns.push(moneyColumn("余额", "balance", "right"))
  return columns
}

export function tableScrollX(dayCount: number): number {
  return 240 + 140 + dayCount * 260 + 420
}

function moneyColumn(title: string, field: string, fixed?: "left" | "right"): TableColumnData {
  return {
    title,
    width: title === "上月余额" || fixed === "right" ? 140 : 130,
    align: "right",
    fixed,
    render: ({ record }: { record: TableData }): VNode => h(MoneyText, { value: readAmount(record, field) }),
  }
}

function readAmount(record: TableData, field: string): string | null {
  const amounts = record.amounts
  if (!isRecord(amounts)) {
    return null
  }
  const value = amounts[field]
  return typeof value === "string" ? value : null
}
