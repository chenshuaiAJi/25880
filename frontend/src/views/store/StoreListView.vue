<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue"
import type { TableColumnData, TableData } from "@arco-design/web-vue/es/table/interface"
import { computed, onMounted, ref } from "vue"
import {
  fetchMergePreview,
  fetchStores,
  mergeStoreRecords,
  patchStore,
  type MergePreview,
  type StoreSummary,
} from "@/api/client"
import { useStoreArchiveStore } from "@/stores/useStoreArchiveStore"
import { monthLabel, sourceLabel } from "@/utils/format"

const store = useStoreArchiveStore()
const saving = ref(false)
const form = ref({
  displayName: "",
  code: "",
  managerName: "",
  phone: "",
  address: "",
})
const mergeTargetId = ref<number | undefined>(undefined)
const mergeCandidates = ref<StoreSummary[]>([])
const mergePreview = ref<MergePreview | null>(null)

const columns: TableColumnData[] = [
  { title: "显示名", dataIndex: "displayName", ellipsis: true, tooltip: true },
  { title: "电话", dataIndex: "phone", width: 140 },
  { title: "地址", dataIndex: "address", ellipsis: true, tooltip: true },
  { title: "发货单", dataIndex: "orderCount", width: 90, align: "right" },
  { title: "汇款行", dataIndex: "remittanceRowCount", width: 90, align: "right" },
]

const aliasRows = computed(() =>
  (store.detail?.aliases ?? []).map((alias) => ({
    ...alias,
    sourceLabel: sourceLabel(alias.source),
  })),
)

const aliasColumns: TableColumnData[] = [
  { title: "原始名称", dataIndex: "rawName" },
  { title: "来源", dataIndex: "sourceLabel", width: 100 },
  { title: "关联单据", dataIndex: "documentCount", width: 100, align: "right" },
]

const candidateOptions = computed(() =>
  mergeCandidates.value
    .filter((item) => item.id !== store.detail?.id)
    .map((item) => ({ value: item.id, label: item.displayName })),
)

onMounted(() => {
  void store.load()
})

async function onSearch(): Promise<void> {
  await store.load()
}

async function openRow(record: TableData): Promise<void> {
  const id = record.id
  if (typeof id !== "number") {
    return
  }
  await store.open(id)
  if (store.detail === null) {
    return
  }
  form.value = {
    displayName: store.detail.displayName,
    code: store.detail.code ?? "",
    managerName: store.detail.managerName ?? "",
    phone: store.detail.phone ?? "",
    address: store.detail.address ?? "",
  }
  mergeTargetId.value = undefined
  mergePreview.value = null
  mergeCandidates.value = await fetchStores("")
}

async function saveProfile(): Promise<void> {
  if (store.detail === null) {
    return
  }
  saving.value = true
  try {
    store.detail = await patchStore(store.detail.id, {
      displayName: form.value.displayName,
      code: form.value.code,
      managerName: form.value.managerName,
      phone: form.value.phone,
      address: form.value.address,
    })
    await store.load()
    Message.success("门店资料已保存")
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "保存失败")
  } finally {
    saving.value = false
  }
}

async function loadMergePreview(): Promise<void> {
  if (store.detail === null || mergeTargetId.value === undefined) {
    return
  }
  try {
    mergePreview.value = await fetchMergePreview(store.detail.id, mergeTargetId.value)
  } catch (error) {
    mergePreview.value = null
    Message.error(error instanceof Error ? error.message : "预览失败")
  }
}

function confirmMerge(): void {
  if (store.detail === null || mergeTargetId.value === undefined || mergePreview.value === null) {
    return
  }
  const preview = mergePreview.value
  const keepId = store.detail.id
  const mergeId = mergeTargetId.value
  const dayHints = preview.overlaps
    .flatMap((item) =>
      item.days.map(
        (day) =>
          `${monthLabel(item.year, item.month)}${day.day}日${day.kind === "remit" ? "汇款" : "发货"}：${day.keepAmount}+${day.mergeAmount}=${day.sumAmount}`,
      ),
    )
    .slice(0, 8)
  Modal.confirm({
    title: "确认合并门店",
    content:
      `保留「${preview.keepStore.displayName}」，并入「${preview.mergeStore.displayName}」。\n` +
      `将迁入发货单 ${preview.orderCount} 张、汇款行 ${preview.remittanceRowCount} 行。\n` +
      (dayHints.length > 0 ? `同日金额将相加：\n${dayHints.join("\n")}` : "没有同日两边都有金额的单元格。"),
    onOk: async () => {
      saving.value = true
      try {
        store.detail = await mergeStoreRecords(keepId, mergeId, form.value.displayName)
        await store.load()
        mergeCandidates.value = await fetchStores("")
        mergeTargetId.value = undefined
        mergePreview.value = null
        Message.success("门店已合并")
      } catch (error) {
        Message.error(error instanceof Error ? error.message : "合并失败")
      } finally {
        saving.value = false
      }
    },
  })
}
</script>

<template>
  <section class="page">
    <header class="toolbar">
      <div>
        <h1>门店</h1>
        <p>导入时发货单和汇款表的原始名称各自成一条。可改显示名，也可合并两家店。</p>
      </div>
      <div class="search">
        <a-input v-model="store.keyword" allow-clear placeholder="显示名或原始名称" @press-enter="onSearch" />
        <a-button type="primary" @click="onSearch">查询</a-button>
      </div>
    </header>
    <a-alert v-if="store.errorMessage" type="error">{{ store.errorMessage }}</a-alert>
    <div class="panel">
      <a-table
        :columns="columns"
        :data="store.items"
        :loading="store.loading"
        :pagination="{ pageSize: 20, showTotal: true }"
        row-key="id"
        @row-click="openRow"
      />
    </div>
    <a-drawer :visible="store.detailVisible" :width="640" title="门店详情" @cancel="store.close">
      <template v-if="store.detail">
        <h2>资料</h2>
        <div class="form">
          <label>显示名<a-input v-model="form.displayName" /></label>
          <label>编号<a-input v-model="form.code" /></label>
          <label>负责人<a-input v-model="form.managerName" /></label>
          <label>电话<a-input v-model="form.phone" /></label>
          <label>地址<a-input v-model="form.address" /></label>
          <a-button type="primary" :loading="saving" @click="saveProfile">保存资料</a-button>
        </div>

        <h2>原始名称</h2>
        <a-table :columns="aliasColumns" :data="aliasRows" :pagination="false" row-key="rawName" />

        <h2>合并到当前门店</h2>
        <div class="merge">
          <a-select
            v-model="mergeTargetId"
            :options="candidateOptions"
            allow-search
            placeholder="选择要并入的门店"
            style="flex: 1"
            @change="loadMergePreview"
          />
          <a-button :disabled="mergePreview === null" :loading="saving" @click="confirmMerge">合并</a-button>
        </div>
        <template v-if="mergePreview">
          <p>
            将并入发货单 {{ mergePreview.orderCount }} 张、汇款行 {{ mergePreview.remittanceRowCount }} 行。
            同日两边都有金额时会相加。
          </p>
          <ul v-if="mergePreview.overlaps.length > 0">
            <li v-for="item in mergePreview.overlaps" :key="`${item.year}-${item.month}`">
              {{ monthLabel(item.year, item.month) }} 期初
              {{ item.keepOpening }} + {{ item.mergeOpening }} = {{ item.sumOpening }}
            </li>
          </ul>
        </template>
      </template>
    </a-drawer>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

h1,
h2 {
  margin: 0;
}

h2 {
  margin-top: 20px;
  margin-bottom: 10px;
}

p {
  margin: 6px 0 0;
}

.search,
.merge {
  display: flex;
  gap: 12px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
}

.form {
  display: grid;
  gap: 12px;
}

.form label {
  display: grid;
  gap: 6px;
  font-size: var(--jl-font-base);
  font-weight: 600;
}

:deep(.arco-table-tr) {
  cursor: pointer;
}
</style>
