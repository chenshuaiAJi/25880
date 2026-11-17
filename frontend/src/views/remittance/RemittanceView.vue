<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue"
import type { TableData } from "@arco-design/web-vue/es/table/interface"
import { computed, onMounted, ref, watch } from "vue"
import { downloadRemittanceExport, fetchStores, type RemittanceRow, type StoreSummary } from "@/api/client"
import { useRemittanceStore } from "@/stores/useRemittanceStore"
import { monthLabel } from "@/utils/format"
import { buildColumns, tableScrollX, toSheetRows } from "@/views/remittance/columns"
import RemittanceEditDrawer from "@/views/remittance/RemittanceEditDrawer.vue"

const store = useRemittanceStore()
const editVisible = ref(false)
const editingRow = ref<RemittanceRow | null>(null)
const exporting = ref(false)
const addVisible = ref(false)
const addMode = ref<"existing" | "new">("existing")
const addStoreId = ref<number | undefined>(undefined)
const addDisplayName = ref("")
const addOpening = ref("")
const allStores = ref<StoreSummary[]>([])

const monthOptions = computed(() =>
  store.months.map((item) => ({
    value: `${item.year}-${item.month}`,
    label: monthLabel(item.year, item.month),
  })),
)

const selectedMonth = computed(() =>
  store.year === null || store.month === null ? undefined : `${store.year}-${store.month}`,
)

const columns = computed(() =>
  store.sheet === null ? [] : buildColumns(store.sheet.dayCount, store.sheet.calendarDays),
)

const rows = computed(() => (store.sheet === null ? [] : toSheetRows(store.sheet.rows)))

const scroll = computed(() => ({
  x: store.sheet === null ? 800 : tableScrollX(store.sheet.dayCount),
  y: "calc(100vh - 220px)",
}))

const hasExtraDays = computed(
  () => store.sheet !== null && store.sheet.dayCount > store.sheet.calendarDays,
)

const existingStoreIds = computed(() => new Set((store.sheet?.rows ?? []).map((row) => row.storeId)))

const availableStoreOptions = computed(() =>
  allStores.value
    .filter((item) => !existingStoreIds.value.has(item.id))
    .map((item) => ({ value: item.id, label: item.displayName })),
)

onMounted(() => {
  void store.loadMonths()
  void fetchStores("").then((rows) => {
    allStores.value = rows
  })
})

watch(
  () => store.sheet,
  () => {
    if (editingRow.value !== null) {
      editingRow.value = store.findRow(editingRow.value.id)
    }
  },
)

async function onMonthChange(value: unknown): Promise<void> {
  if (typeof value !== "string") {
    return
  }
  await store.selectMonth(value)
}

function openRow(record: TableData): void {
  const rowId = record.rowId
  if (typeof rowId !== "number") {
    return
  }
  editingRow.value = store.findRow(rowId)
  editVisible.value = true
}

function closeEdit(): void {
  editVisible.value = false
  editingRow.value = store.sheet === null || editingRow.value === null
    ? null
    : store.findRow(editingRow.value.id)
}

async function onExport(): Promise<void> {
  if (store.year === null || store.month === null || store.sheet === null) {
    Message.warning("请先选择要导出的月份")
    return
  }
  exporting.value = true
  try {
    await downloadRemittanceExport(store.year, store.month)
    Message.success(`已导出 ${monthLabel(store.year, store.month)}`)
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "导出失败")
  } finally {
    exporting.value = false
  }
}

async function onCreateNext(): Promise<void> {
  try {
    const preview = await store.loadNextPreview()
    if (!preview.canCreate) {
      Modal.warning({
        title: "不能创建下月报表",
        content: preview.blockers.join("；"),
      })
      return
    }
    const gapText =
      preview.openingGaps.length === 0
        ? ""
        : `\n\n当前月相对上一期仍有 ${preview.openingGaps.length} 家店期初不平。继续创建不会自动改这些期初。`
    Modal.confirm({
      title: "创建下月报表",
      content: `${preview.message}\n将带入 ${preview.storeCount} 家店，每日金额为空，期初等于本月余额。${gapText}`,
      onOk: async () => {
        try {
          await store.createNext(preview.openingGaps.length > 0)
          Message.success("下月报表已创建")
        } catch {
          Message.error(store.errorMessage || "创建失败")
        }
      },
    })
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "预览失败")
  }
}

async function onApplyOpening(): Promise<void> {
  if (store.openingGaps.length === 0) {
    return
  }
  Modal.confirm({
    title: "用上月余额覆盖本月期初",
    content: `将覆盖 ${store.openingGaps.length} 家店的上月余额。未确认前系统不会自动改。`,
    onOk: async () => {
      try {
        await store.applyOpenings(null)
        Message.success("期初已覆盖")
      } catch {
        Message.error(store.errorMessage || "覆盖失败")
      }
    },
  })
}

async function openAddStore(): Promise<void> {
  if (store.sheet === null) {
    Message.warning("请先选择有汇款表的月份")
    return
  }
  allStores.value = await fetchStores("")
  addMode.value = "existing"
  addStoreId.value = undefined
  addDisplayName.value = ""
  addOpening.value = ""
  addVisible.value = true
}

async function submitAddStore(): Promise<boolean> {
  try {
    if (addMode.value === "existing") {
      if (addStoreId.value === undefined) {
        Message.warning("请选择门店")
        return false
      }
      await store.addStoreRow({
        storeId: addStoreId.value,
        openingBalance: addOpening.value.trim() === "" ? undefined : addOpening.value.trim(),
      })
    } else {
      const name = addDisplayName.value.trim()
      if (name === "") {
        Message.warning("请填写新门店名称")
        return false
      }
      await store.addStoreRow({
        displayName: name,
        openingBalance: addOpening.value.trim() === "" ? undefined : addOpening.value.trim(),
      })
      allStores.value = await fetchStores("")
    }
    Message.success("已增加到本月汇款表")
    addVisible.value = false
    return true
  } catch {
    Message.error(store.errorMessage || "增加门店失败")
    return false
  }
}
</script>

<template>
  <section class="page">
    <header class="toolbar">
      <div>
        <h1>汇款月表</h1>
        <p>
          一行一家店。点门店行可手改任意一天的汇款/发货（临时加货就改「发货」）。发货单金额不会自动覆盖这里。
          余额 = 上月余额 + 汇款总额 − 发货总额。
        </p>
      </div>
      <div class="actions">
        <a-select
          :model-value="selectedMonth"
          :options="monthOptions"
          placeholder="选择月份"
          style="width: 200px"
          @change="onMonthChange"
        />
        <a-button :loading="exporting" :disabled="store.sheet === null" @click="onExport">导出 Excel</a-button>
        <a-button type="outline" :disabled="store.sheet === null" @click="openAddStore">增加门店</a-button>
        <a-button :loading="store.saving" @click="onCreateNext">创建下月报表</a-button>
      </div>
    </header>
    <p v-if="hasExtraDays" class="hint">带 * 的日期超出该月公历天数。原表模板仍保留这些列，总额按表上的列计算。</p>
    <a-alert v-if="store.openingGaps.length > 0" type="warning">
      有 {{ store.openingGaps.length }} 家店的上月余额与本月期初不平。
      <a-button type="text" @click="onApplyOpening">用上月余额覆盖</a-button>
    </a-alert>
    <a-alert v-if="store.errorMessage" type="error">{{ store.errorMessage }}</a-alert>
    <a-spin :loading="store.loading" class="panel">
      <a-empty v-if="store.months.length === 0 && !store.loading" description="还没有汇款月表，请先到导入页导入 Excel" />
      <a-table
        v-else
        :columns="columns"
        :data="rows"
        :pagination="false"
        :scroll="scroll"
        row-key="key"
        :bordered="{ wrapper: true, cell: true }"
        @row-click="openRow"
      >
        <template #empty>
          <a-empty description="这个月没有门店行" />
        </template>
      </a-table>
    </a-spin>
    <RemittanceEditDrawer
      :visible="editVisible"
      :row="editingRow"
      :day-count="store.sheet?.dayCount ?? 31"
      @close="closeEdit"
    />
    <a-modal
      v-model:visible="addVisible"
      title="增加到本月汇款表"
      :ok-loading="store.saving"
      ok-text="确定增加"
      :on-before-ok="submitAddStore"
    >
      <div class="add-form">
        <a-radio-group v-model="addMode" type="button">
          <a-radio value="existing">已有门店</a-radio>
          <a-radio value="new">新建门店</a-radio>
        </a-radio-group>
        <template v-if="addMode === 'existing'">
          <label>选择门店</label>
          <a-select
            v-model="addStoreId"
            :options="availableStoreOptions"
            allow-search
            placeholder="只列出本月还没有的门店"
            style="width: 100%"
          />
        </template>
        <template v-else>
          <label>新门店名称</label>
          <a-input v-model="addDisplayName" placeholder="例如：某某超市（临时加货）" allow-clear />
        </template>
        <label>上月余额（可选）</label>
        <a-input v-model="addOpening" placeholder="留空则沿用上月余额，没有上月则为 0" allow-clear />
        <p class="hint">增加后可在该行里手填每天汇款/发货。同一家店本月只能有一行。</p>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 100%;
  min-width: 0;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

h1 {
  margin: 0;
}

p {
  margin: 6px 0 0;
}

.hint {
  margin: 0;
}

.panel {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  background: #fff;
  border-radius: 10px;
  padding: 16px;
}

:deep(.arco-table-tr) {
  cursor: pointer;
}

.add-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.add-form label {
  font-size: var(--jl-font-base);
  font-weight: 600;
  color: var(--color-text-1);
}
</style>
