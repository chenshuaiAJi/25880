<script setup lang="ts">
import type { TableColumnData, TableData } from "@arco-design/web-vue/es/table/interface"
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import MoneyText from "@/components/MoneyText.vue"
import { useShipmentStore } from "@/stores/useShipmentStore"
import { batchLabel, monthLabel } from "@/utils/format"

const store = useShipmentStore()
const router = useRouter()
const dateRange = ref<string[]>([])

const monthOptions = computed(() => [
  { value: "", label: "全部月份" },
  ...store.months.map((item) => ({
    value: `${item.year}-${item.month}`,
    label: `${monthLabel(item.year, item.month)}（${item.orderCount}单）`,
  })),
])

const storeOptions = computed(() =>
  store.stores.map((item) => ({ value: item.id, label: item.displayName })),
)

const batchOptions = [
  { value: 0, label: "无括号" },
  { value: 1, label: "(1)" },
  { value: 2, label: "(2)" },
  { value: 3, label: "(3)" },
  { value: 4, label: "(4)" },
  { value: 102, label: "B" },
]

const rows = computed(() =>
  store.items.map((item) => ({
    ...item,
    batchLabel: batchLabel(item.batchNo, item.batchLabel),
  })),
)

const columns: TableColumnData[] = [
  { title: "业务日", dataIndex: "bizDate", width: 120 },
  { title: "门店", dataIndex: "displayName", ellipsis: true, tooltip: true },
  { title: "原始客户名", dataIndex: "customerRawName", ellipsis: true, tooltip: true },
  { title: "文件", dataIndex: "fileName", width: 140 },
  { title: "批次", dataIndex: "batchLabel", width: 90 },
  { title: "行数", dataIndex: "lineCount", width: 80, align: "right" },
  { title: "金额", slotName: "amount", width: 120, align: "right" },
]

const selectedMonth = computed(() =>
  store.year === undefined || store.month === undefined ? "" : `${store.year}-${store.month}`,
)

onMounted(() => {
  void store.loadFilters().then(() => store.loadList())
})

async function onMonthChange(value: unknown): Promise<void> {
  if (typeof value !== "string" || value === "") {
    store.year = undefined
    store.month = undefined
    return
  }
  const [yearText, monthText] = value.split("-")
  store.year = Number(yearText)
  store.month = Number(monthText)
}

async function onSearch(): Promise<void> {
  store.dateFrom = dateRange.value[0] ?? ""
  store.dateTo = dateRange.value[1] ?? ""
  await store.search()
}

async function onPageChange(page: number): Promise<void> {
  await store.changePage(page)
}

function openRow(record: TableData): void {
  const id = record.id
  if (typeof id === "number") {
    void router.push(`/shipments/${id}`)
  }
}
</script>

<template>
  <section class="page">
    <header>
      <h1>发货单</h1>
      <p>业务日按月份目录和文件名起始日。点一行查看商品明细。</p>
    </header>
    <a-alert v-if="store.errorMessage" type="error">{{ store.errorMessage }}</a-alert>
    <div class="filters">
      <a-select :model-value="selectedMonth" :options="monthOptions" style="width: 220px" @change="onMonthChange" />
      <a-range-picker v-model="dateRange" value-format="YYYY-MM-DD" style="width: 260px" />
      <a-select
        v-model="store.batchNo"
        :options="batchOptions"
        allow-clear
        placeholder="批次"
        style="width: 120px"
      />
      <a-select
        v-model="store.storeId"
        :options="storeOptions"
        allow-clear
        allow-search
        placeholder="门店"
        style="width: 220px"
      />
      <a-input v-model="store.keyword" allow-clear placeholder="门店或原始名称" style="width: 200px" @press-enter="onSearch" />
      <a-button type="primary" @click="onSearch">查询</a-button>
    </div>
    <div class="panel">
      <a-table
        :columns="columns"
        :data="rows"
        :loading="store.loading"
        :pagination="false"
        row-key="id"
        @row-click="openRow"
      >
        <template #amount="{ record }">
          <MoneyText :value="typeof record.totalAmount === 'string' ? record.totalAmount : null" />
        </template>
      </a-table>
      <div class="pager">
        <a-pagination
          :current="store.page"
          :page-size="store.pageSize"
          :total="store.total"
          show-total
          @change="onPageChange"
        />
      </div>
    </div>
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

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

:deep(.arco-table-tr) {
  cursor: pointer;
}
</style>
