<script setup lang="ts">
import { Message } from "@arco-design/web-vue"
import type { TableColumnData } from "@arco-design/web-vue/es/table/interface"
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  fetchStores,
  patchShipmentLine,
  reassignShipmentOrder,
  type StoreSummary,
} from "@/api/client"
import MoneyText from "@/components/MoneyText.vue"
import { useShipmentStore } from "@/stores/useShipmentStore"
import { batchLabel } from "@/utils/format"

const route = useRoute()
const router = useRouter()
const store = useShipmentStore()
const saving = ref(false)
const stores = ref<StoreSummary[]>([])
const targetStoreId = ref<number | undefined>(undefined)
const syncMode = ref<"one" | "all">("one")
const drafts = ref<Record<number, { shipQty: string; unitPrice: string; amount: string }>>({})

const orderId = computed(() => {
  const raw = route.params.id
  const text = Array.isArray(raw) ? raw[0] : raw
  const id = Number(text)
  return Number.isInteger(id) && id > 0 ? id : null
})

const batchText = computed(() =>
  store.detail === null ? "" : batchLabel(store.detail.batchNo, store.detail.batchLabel),
)

const storeOptions = computed(() => stores.value.map((item) => ({ value: item.id, label: item.displayName })))

const columns: TableColumnData[] = [
  { title: "品名", dataIndex: "productName" },
  { title: "单位", dataIndex: "unit", width: 80 },
  { title: "订单数量", dataIndex: "orderQty", width: 100, align: "right" },
  { title: "发货数量", slotName: "shipQty", width: 120, align: "right" },
  { title: "单价", slotName: "unitPrice", width: 120, align: "right" },
  { title: "金额", slotName: "amount", width: 140, align: "right" },
]

onMounted(() => {
  void fetchStores("").then((rows) => {
    stores.value = rows
  })
  if (orderId.value !== null) {
    void store.loadDetail(orderId.value)
  }
})

watch(
  () => store.detail,
  (detail) => {
    if (detail === null) {
      drafts.value = {}
      return
    }
    targetStoreId.value = detail.storeId
    const next: Record<number, { shipQty: string; unitPrice: string; amount: string }> = {}
    for (const line of detail.lines) {
      next[line.lineIndex] = {
        shipQty: line.shipQty ?? "",
        unitPrice: line.unitPrice ?? "",
        amount: line.amount ?? "",
      }
    }
    drafts.value = next
  },
)

function goBack(): void {
  void router.push("/shipments")
}

async function saveLine(lineIndex: number, edited: "qty" | "price" | "amount"): Promise<void> {
  if (orderId.value === null || store.detail === null) {
    return
  }
  const draft = drafts.value[lineIndex]
  const original = store.detail.lines.find((line) => line.lineIndex === lineIndex)
  if (draft === undefined || original === undefined) {
    return
  }
  const before =
    edited === "qty" ? (original.shipQty ?? "") : edited === "price" ? (original.unitPrice ?? "") : (original.amount ?? "")
  const after = edited === "qty" ? draft.shipQty : edited === "price" ? draft.unitPrice : draft.amount
  if (before === after) {
    return
  }
  saving.value = true
  try {
    const detail = await patchShipmentLine(orderId.value, lineIndex, {
      shipQty: draft.shipQty,
      unitPrice: draft.unitPrice,
      amount: draft.amount,
      edited,
    })
    store.detail = detail
    Message.success("已保存并重算")
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "保存失败")
  } finally {
    saving.value = false
  }
}

async function reassign(): Promise<void> {
  if (orderId.value === null || targetStoreId.value === undefined) {
    return
  }
  saving.value = true
  try {
    store.detail = await reassignShipmentOrder(orderId.value, targetStoreId.value, syncMode.value)
    Message.success(syncMode.value === "one" ? "已改挂这一单" : "已同步该原始名称下全部发货单")
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "改挂失败")
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="page">
    <a-button type="text" @click="goBack">返回列表</a-button>
    <a-alert v-if="store.errorMessage" type="error">{{ store.errorMessage }}</a-alert>
    <a-spin :loading="store.detailLoading">
      <template v-if="store.detail">
        <header>
          <h1>{{ store.detail.displayName }}</h1>
          <p>{{ store.detail.bizDate }} · {{ store.detail.fileName }} · 批次 {{ batchText }}</p>
        </header>
        <a-descriptions :column="2" bordered class="meta">
          <a-descriptions-item label="原始客户名">{{ store.detail.customerRawName }}</a-descriptions-item>
          <a-descriptions-item label="市场">{{ store.detail.marketName }}</a-descriptions-item>
          <a-descriptions-item label="电话">{{ store.detail.phone }}</a-descriptions-item>
          <a-descriptions-item label="地址">{{ store.detail.address }}</a-descriptions-item>
          <a-descriptions-item label="单元格发货日期">{{ store.detail.shipDateText }}</a-descriptions-item>
          <a-descriptions-item label="合计">
            <MoneyText :value="store.detail.totalAmount" />
          </a-descriptions-item>
        </a-descriptions>

        <div class="reassign">
          <span>改挂门店</span>
          <a-select v-model="targetStoreId" :options="storeOptions" allow-search style="width: 240px" />
          <a-select v-model="syncMode" style="width: 140px">
            <a-option value="one">只改这一单</a-option>
            <a-option value="all">同步全部</a-option>
          </a-select>
          <a-button :loading="saving" @click="reassign">改挂</a-button>
        </div>

        <a-table :columns="columns" :data="store.detail.lines" :pagination="false" row-key="lineIndex">
          <template #shipQty="{ record }">
            <a-input
              v-if="typeof record.lineIndex === 'number' && drafts[record.lineIndex]"
              v-model="drafts[record.lineIndex].shipQty"
              size="mini"
              @press-enter="saveLine(record.lineIndex, 'qty')"
              @blur="saveLine(record.lineIndex, 'qty')"
            />
          </template>
          <template #unitPrice="{ record }">
            <a-input
              v-if="typeof record.lineIndex === 'number' && drafts[record.lineIndex]"
              v-model="drafts[record.lineIndex].unitPrice"
              size="mini"
              @press-enter="saveLine(record.lineIndex, 'price')"
              @blur="saveLine(record.lineIndex, 'price')"
            />
          </template>
          <template #amount="{ record }">
            <a-input
              v-if="typeof record.lineIndex === 'number' && drafts[record.lineIndex]"
              v-model="drafts[record.lineIndex].amount"
              size="mini"
              @press-enter="saveLine(record.lineIndex, 'amount')"
              @blur="saveLine(record.lineIndex, 'amount')"
            />
          </template>
        </a-table>
        <p class="hint">改数量或单价会重算金额；直接改金额会反推单价。仅改发货单不会覆盖汇款表「发货」列。</p>
      </template>
    </a-spin>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

h1 {
  margin: 0;
}

p {
  margin: 6px 0 0;
}

.meta,
.reassign {
  background: #fff;
}

.reassign {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px;
  border-radius: 10px;
}

.hint {
  margin: 0;
}
</style>
