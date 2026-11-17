import { defineStore } from "pinia"
import { ref } from "vue"
import {
  fetchShipment,
  fetchShipmentMonths,
  fetchShipments,
  fetchStores,
  type ShipmentDetail,
  type ShipmentListItem,
  type ShipmentMonth,
  type StoreSummary,
} from "@/api/client"

export const useShipmentStore = defineStore("shipment", () => {
  const months = ref<ShipmentMonth[]>([])
  const stores = ref<StoreSummary[]>([])
  const items = ref<ShipmentListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const year = ref<number | undefined>(undefined)
  const month = ref<number | undefined>(undefined)
  const dateFrom = ref("")
  const dateTo = ref("")
  const batchNo = ref<number | undefined>(undefined)
  const storeId = ref<number | undefined>(undefined)
  const keyword = ref("")
  const loading = ref(false)
  const detail = ref<ShipmentDetail | null>(null)
  const detailLoading = ref(false)
  const errorMessage = ref("")

  async function loadFilters(): Promise<void> {
    const [monthRows, storeRows] = await Promise.all([fetchShipmentMonths(), fetchStores("")])
    months.value = monthRows
    stores.value = storeRows
  }

  async function loadList(): Promise<void> {
    loading.value = true
    errorMessage.value = ""
    try {
      const result = await fetchShipments({
        year: year.value,
        month: month.value,
        dateFrom: dateFrom.value || undefined,
        dateTo: dateTo.value || undefined,
        batchNo: batchNo.value,
        storeId: storeId.value,
        keyword: keyword.value,
        page: page.value,
        pageSize: pageSize.value,
      })
      items.value = result.items
      total.value = result.total
    } catch (error) {
      items.value = []
      total.value = 0
      errorMessage.value = error instanceof Error ? error.message : "加载发货单失败"
    } finally {
      loading.value = false
    }
  }

  async function search(): Promise<void> {
    page.value = 1
    await loadList()
  }

  async function changePage(nextPage: number): Promise<void> {
    page.value = nextPage
    await loadList()
  }

  async function loadDetail(id: number): Promise<void> {
    detailLoading.value = true
    errorMessage.value = ""
    detail.value = null
    try {
      detail.value = await fetchShipment(id)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "加载明细失败"
    } finally {
      detailLoading.value = false
    }
  }

  return {
    months,
    stores,
    items,
    total,
    page,
    pageSize,
    year,
    month,
    dateFrom,
    dateTo,
    batchNo,
    storeId,
    keyword,
    loading,
    detail,
    detailLoading,
    errorMessage,
    loadFilters,
    loadList,
    search,
    changePage,
    loadDetail,
  }
})
