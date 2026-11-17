import { defineStore } from "pinia"
import { ref } from "vue"
import { fetchStore, fetchStores, type StoreDetail, type StoreSummary } from "@/api/client"

export const useStoreArchiveStore = defineStore("store-archive", () => {
  const items = ref<StoreSummary[]>([])
  const keyword = ref("")
  const loading = ref(false)
  const detail = ref<StoreDetail | null>(null)
  const detailVisible = ref(false)
  const errorMessage = ref("")

  async function load(): Promise<void> {
    loading.value = true
    errorMessage.value = ""
    try {
      items.value = await fetchStores(keyword.value)
    } catch (error) {
      items.value = []
      errorMessage.value = error instanceof Error ? error.message : "加载门店失败"
    } finally {
      loading.value = false
    }
  }

  async function open(id: number): Promise<void> {
    detailVisible.value = true
    detail.value = null
    try {
      detail.value = await fetchStore(id)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "加载门店详情失败"
    }
  }

  function close(): void {
    detailVisible.value = false
  }

  return {
    items,
    keyword,
    loading,
    detail,
    detailVisible,
    errorMessage,
    load,
    open,
    close,
  }
})
