import { defineStore } from "pinia"
import { ref } from "vue"
import {
  addRemittanceRow,
  applyOpeningBalances,
  createNextMonthSheet,
  fetchNextMonthPreview,
  fetchOpeningMismatches,
  fetchRemittanceMonths,
  fetchRemittanceSheet,
  patchRemittanceCell,
  patchRemittanceOpening,
  reassignRemittanceRow,
  type NextMonthPreview,
  type OpeningMismatch,
  type RemittanceMonth,
  type RemittanceRow,
  type RemittanceSheet,
} from "@/api/client"

export const useRemittanceStore = defineStore("remittance", () => {
  const months = ref<RemittanceMonth[]>([])
  const year = ref<number | null>(null)
  const month = ref<number | null>(null)
  const sheet = ref<RemittanceSheet | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const errorMessage = ref("")
  const nextPreview = ref<NextMonthPreview | null>(null)
  const openingGaps = ref<OpeningMismatch[]>([])

  async function loadMonths(): Promise<void> {
    loading.value = true
    errorMessage.value = ""
    try {
      months.value = await fetchRemittanceMonths()
      const latest = months.value.at(-1)
      if (latest && year.value === null) {
        year.value = latest.year
        month.value = latest.month
        await loadSheet()
      }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "加载月份失败"
    } finally {
      loading.value = false
    }
  }

  async function loadSheet(): Promise<void> {
    if (year.value === null || month.value === null) {
      sheet.value = null
      return
    }
    loading.value = true
    errorMessage.value = ""
    try {
      sheet.value = await fetchRemittanceSheet(year.value, month.value)
      openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
    } catch (error) {
      sheet.value = null
      errorMessage.value = error instanceof Error ? error.message : "加载汇款月表失败"
    } finally {
      loading.value = false
    }
  }

  async function selectMonth(value: string): Promise<void> {
    const [yearText, monthText] = value.split("-")
    const nextYear = Number(yearText)
    const nextMonth = Number(monthText)
    if (!Number.isInteger(nextYear) || !Number.isInteger(nextMonth)) {
      return
    }
    year.value = nextYear
    month.value = nextMonth
    await loadSheet()
  }

  function findRow(rowId: number): RemittanceRow | null {
    return sheet.value?.rows.find((row) => row.id === rowId) ?? null
  }

  async function saveOpening(rowId: number, openingBalance: string): Promise<void> {
    saving.value = true
    errorMessage.value = ""
    try {
      sheet.value = await patchRemittanceOpening(rowId, openingBalance)
      if (year.value !== null && month.value !== null) {
        openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
      }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "保存上月余额失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  async function saveCell(rowId: number, day: number, kind: "remit" | "ship", amount: string | null): Promise<void> {
    saving.value = true
    errorMessage.value = ""
    try {
      sheet.value = await patchRemittanceCell(rowId, day, kind, amount)
      if (year.value !== null && month.value !== null) {
        openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
      }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "保存金额失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  async function reassignRow(rowId: number, storeId: number, mode: "one" | "all"): Promise<void> {
    saving.value = true
    errorMessage.value = ""
    try {
      sheet.value = await reassignRemittanceRow(rowId, storeId, mode)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "改挂门店失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  async function addStoreRow(payload: {
    storeId?: number
    displayName?: string
    openingBalance?: string
  }): Promise<void> {
    if (year.value === null || month.value === null) {
      throw new Error("请先选择月份")
    }
    saving.value = true
    errorMessage.value = ""
    try {
      sheet.value = await addRemittanceRow(year.value, month.value, payload)
      openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "增加门店失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  async function loadNextPreview(): Promise<NextMonthPreview> {
    if (year.value === null || month.value === null) {
      throw new Error("请先选择月份")
    }
    nextPreview.value = await fetchNextMonthPreview(year.value, month.value)
    return nextPreview.value
  }

  async function createNext(continueWithGaps: boolean): Promise<void> {
    if (year.value === null || month.value === null) {
      throw new Error("请先选择月份")
    }
    saving.value = true
    errorMessage.value = ""
    try {
      const created = await createNextMonthSheet(year.value, month.value, continueWithGaps)
      months.value = await fetchRemittanceMonths()
      year.value = created.sheet.year
      month.value = created.sheet.month
      sheet.value = created.sheet
      openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "创建下月报表失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  async function applyOpenings(storeIds: number[] | null): Promise<void> {
    if (year.value === null || month.value === null) {
      return
    }
    saving.value = true
    errorMessage.value = ""
    try {
      sheet.value = await applyOpeningBalances(year.value, month.value, storeIds)
      openingGaps.value = await fetchOpeningMismatches(year.value, month.value)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "覆盖期初失败"
      throw error
    } finally {
      saving.value = false
    }
  }

  return {
    months,
    year,
    month,
    sheet,
    loading,
    saving,
    errorMessage,
    nextPreview,
    openingGaps,
    loadMonths,
    loadSheet,
    selectMonth,
    findRow,
    saveOpening,
    saveCell,
    reassignRow,
    addStoreRow,
    loadNextPreview,
    createNext,
    applyOpenings,
  }
})