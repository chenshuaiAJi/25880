<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue"
import type { FileItem, RequestOption, UploadRequest } from "@arco-design/web-vue/es/upload/interfaces"
import type { TableColumnData } from "@arco-design/web-vue/es/table/interface"
import { computed, onMounted, ref } from "vue"
import {
  assignBankTransaction,
  fetchBankGaps,
  fetchBankTransactions,
  fetchStores,
  importBankFile,
  suggestBankMatches,
  writebackBankRemittance,
  type BankGap,
  type BankTransaction,
  type StoreSummary,
} from "@/api/client"
import MoneyText from "@/components/MoneyText.vue"

const loading = ref(false)
const items = ref<BankTransaction[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const direction = ref<string | undefined>("in")
const matchStatus = ref<string | undefined>(undefined)
const selectedFileName = ref("")
const gaps = ref<BankGap[]>([])
const gapYear = ref(2026)
const gapMonth = ref(11)
const errorMessage = ref("")
const stores = ref<StoreSummary[]>([])

const matchVisible = ref(false)
const matchSaving = ref(false)
const matchTarget = ref<BankTransaction | null>(null)
const matchStoreId = ref<number | undefined>(undefined)
const matchDate = ref("")

const storeOptions = computed(() =>
  stores.value.map((store) => ({
    value: store.id,
    label: store.displayName,
  })),
)

const columns: TableColumnData[] = [
  { title: "日期", dataIndex: "txnDate", width: 110 },
  { title: "时间", dataIndex: "txnTime", width: 90 },
  { title: "金额", slotName: "amount", width: 110, align: "right" },
  { title: "方向", slotName: "direction", width: 70 },
  { title: "对方户名", dataIndex: "counterpartyName", ellipsis: true, tooltip: true },
  { title: "用途", dataIndex: "purpose", width: 120, ellipsis: true, tooltip: true },
  { title: "状态", slotName: "status", width: 100 },
  { title: "归属门店", dataIndex: "displayName", ellipsis: true, tooltip: true },
  { title: "归属日", dataIndex: "matchedDate", width: 110 },
  { title: "操作", slotName: "actions", width: 220 },
]

const gapColumns: TableColumnData[] = [
  { title: "日期", dataIndex: "date", width: 120 },
  { title: "门店", dataIndex: "displayName" },
  { title: "流水合计", slotName: "bankTotal", width: 120, align: "right" },
  { title: "汇款表", slotName: "remitAmount", width: 120, align: "right" },
  { title: "差额", slotName: "difference", width: 120, align: "right" },
  { title: "操作", slotName: "actions", width: 140 },
]

onMounted(() => {
  void fetchStores("").then((rows) => {
    stores.value = rows
  })
  void load()
  void loadGaps()
})

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ""
  try {
    const result = await fetchBankTransactions({
      direction: direction.value,
      matchStatus: matchStatus.value,
      page: page.value,
      pageSize,
    })
    items.value = result.items
    total.value = result.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "加载流水失败"
  } finally {
    loading.value = false
  }
}

async function loadGaps(): Promise<void> {
  try {
    gaps.value = await fetchBankGaps(gapYear.value, gapMonth.value)
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "加载差额失败")
  }
}

function customUpload(option: RequestOption): UploadRequest {
  const file = option.fileItem.file
  if (!(file instanceof File)) {
    option.onError(new Error("请选择本地文件"))
    return {}
  }
  loading.value = true
  selectedFileName.value = file.name
  void (async () => {
    try {
      const result = await importBankFile(file)
      Message.success(
        `已导入 ${String(result.inserted)} 笔，跳过重复 ${String(result.skippedDuplicates)}，建议匹配 ${String(result.suggested)}`,
      )
      option.onSuccess(result)
      page.value = 1
      await load()
      await loadGaps()
    } catch (error) {
      const message = error instanceof Error ? error.message : "导入失败"
      Message.error(message)
      option.onError(error instanceof Error ? error : new Error(message))
    } finally {
      loading.value = false
    }
  })()
  return {}
}

function beforeUpload(file: File): boolean {
  const name = file.name.toLowerCase()
  if (!name.endsWith(".xlsx") && !name.endsWith(".xls")) {
    Message.warning("请选择银行下载的 .xlsx / .xls 明细")
    return false
  }
  return true
}

function onUploadChange(_: FileItem[], current: FileItem): void {
  if (current?.file?.name) {
    selectedFileName.value = current.file.name
  }
}

async function onSuggest(): Promise<void> {
  try {
    const count = await suggestBankMatches()
    Message.success(`已生成 ${count} 条建议匹配`)
    await load()
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "匹配失败")
  }
}

function openManualMatch(record: BankTransaction): void {
  matchTarget.value = record
  matchStoreId.value = record.storeId ?? undefined
  matchDate.value = record.matchedDate ?? record.txnDate
  matchVisible.value = true
}

function confirmSuggested(record: BankTransaction): void {
  if (record.storeId === null || record.matchedDate === null) {
    openManualMatch(record)
    return
  }
  Modal.confirm({
    title: "确认匹配",
    content: `确认把 ${record.counterpartyName ?? ""} ${record.amount} 记到 ${record.displayName} / ${record.matchedDate}？确认后才会进入回写候选。`,
    onOk: async () => {
      try {
        await assignBankTransaction(record.id, record.storeId as number, record.matchedDate as string, true)
        Message.success("已确认匹配")
        await load()
        await loadGaps()
      } catch (error) {
        Message.error(error instanceof Error ? error.message : "确认失败")
      }
    },
  })
}

async function saveManualMatch(): Promise<void> {
  const target = matchTarget.value
  if (target === null) {
    return
  }
  if (matchStoreId.value === undefined || !matchDate.value) {
    Message.warning("请选择门店和归属日")
    return
  }
  matchSaving.value = true
  try {
    await assignBankTransaction(target.id, matchStoreId.value, matchDate.value, true)
    Message.success("已手动匹配并确认")
    matchVisible.value = false
    await load()
    await loadGaps()
  } catch (error) {
    Message.error(error instanceof Error ? error.message : "匹配失败")
  } finally {
    matchSaving.value = false
  }
}

function writeback(gap: BankGap): void {
  Modal.confirm({
    title: "回写汇款表",
    content: `用流水合计 ${gap.bankTotal} 覆盖 ${gap.displayName} 在 ${gap.date} 的「汇款」列？`,
    onOk: async () => {
      try {
        await writebackBankRemittance(gap.storeId, gap.date)
        Message.success("已回写汇款表")
        await loadGaps()
      } catch (error) {
        Message.error(error instanceof Error ? error.message : "回写失败")
      }
    },
  })
}

function statusLabel(status: string): string {
  if (status === "suggested") return "建议"
  if (status === "confirmed") return "已确认"
  if (status === "ignored") return "忽略"
  return "未匹配"
}

function canManualMatch(record: BankTransaction): boolean {
  return record.direction === "in" && record.matchStatus !== "ignored"
}
</script>

<template>
  <section class="page">
    <header>
      <h1>银行流水</h1>
      <p>
        手动选择银行下载的交易明细上传导入。支出不进门店汇款；未匹配收入可手动指定门店与归属日，建议项可直接确认或改匹配。
      </p>
    </header>
    <a-alert v-if="errorMessage" type="error">{{ errorMessage }}</a-alert>
    <div class="toolbar">
      <a-upload
        :custom-request="customUpload"
        :show-file-list="false"
        accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
        :disabled="loading"
        :before-upload="beforeUpload"
        @change="onUploadChange"
      >
        <template #upload-button>
          <a-button type="primary" :loading="loading">选择本地文件导入</a-button>
        </template>
      </a-upload>
      <span v-if="selectedFileName" class="file-hint">最近导入：{{ selectedFileName }}</span>
      <a-button :loading="loading" @click="onSuggest">重新建议匹配</a-button>
      <a-select
        v-model="direction"
        allow-clear
        placeholder="方向"
        style="width: 140px"
        :options="[
          { value: 'in', label: '收入' },
          { value: 'out', label: '支出' },
        ]"
        @change="load"
      />
      <a-select
        v-model="matchStatus"
        allow-clear
        placeholder="状态"
        style="width: 140px"
        :options="[
          { value: 'unmatched', label: '未匹配' },
          { value: 'suggested', label: '建议' },
          { value: 'confirmed', label: '已确认' },
        ]"
        @change="load"
      />
    </div>
    <div class="panel">
      <a-table :columns="columns" :data="items" :loading="loading" :pagination="false" row-key="id">
        <template #amount="{ record }">
          <MoneyText :value="typeof record.amount === 'string' ? record.amount : null" />
        </template>
        <template #direction="{ record }">
          {{ record.direction === "in" ? "收入" : "支出" }}
        </template>
        <template #status="{ record }">
          {{ statusLabel(String(record.matchStatus)) }}
        </template>
        <template #actions="{ record }">
          <template v-if="canManualMatch(record)">
            <a-button
              v-if="record.matchStatus === 'suggested'"
              type="text"
              size="mini"
              @click="confirmSuggested(record)"
            >
              确认匹配
            </a-button>
            <a-button type="text" size="mini" @click="openManualMatch(record)">
              {{ record.matchStatus === "unmatched" ? "手动匹配" : "改匹配" }}
            </a-button>
          </template>
          <span v-else>{{ statusLabel(String(record.matchStatus)) }}</span>
        </template>
      </a-table>
      <div class="pager">
        <a-pagination
          :current="page"
          :page-size="pageSize"
          :total="total"
          show-total
          @change="
            (value: number) => {
              page = value
              void load()
            }
          "
        />
      </div>
    </div>

    <div class="panel">
      <div class="toolbar">
        <h2>已确认流水 vs 汇款表</h2>
        <a-input-number v-model="gapYear" :min="2020" :max="2100" />
        <a-input-number v-model="gapMonth" :min="1" :max="12" />
        <a-button @click="loadGaps">刷新差额</a-button>
      </div>
      <a-table
        :columns="gapColumns"
        :data="gaps"
        :pagination="false"
        :row-key="(record: BankGap) => `${record.storeId}-${record.date}`"
      >
        <template #bankTotal="{ record }">
          <MoneyText :value="typeof record.bankTotal === 'string' ? record.bankTotal : null" />
        </template>
        <template #remitAmount="{ record }">
          <MoneyText :value="typeof record.remitAmount === 'string' ? record.remitAmount : null" />
        </template>
        <template #difference="{ record }">
          <MoneyText :value="typeof record.difference === 'string' ? record.difference : null" />
        </template>
        <template #actions="{ record }">
          <a-button type="text" size="mini" @click="writeback(record)">按流水回写汇款</a-button>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:visible="matchVisible"
      title="手动匹配门店"
      :ok-loading="matchSaving"
      ok-text="确认匹配"
      @ok="saveManualMatch"
    >
      <div v-if="matchTarget" class="match-form">
        <p>
          {{ matchTarget.txnDate }} · {{ matchTarget.counterpartyName ?? "无对方户名" }} ·
          {{ matchTarget.amount }}
        </p>
        <label>归属门店</label>
        <a-select
          v-model="matchStoreId"
          :options="storeOptions"
          allow-search
          placeholder="搜索门店"
          style="width: 100%"
        />
        <label>归属日</label>
        <a-date-picker v-model="matchDate" style="width: 100%" value-format="YYYY-MM-DD" />
        <p class="hint">保存后直接记为已确认，可进入下方差额核对与回写。</p>
      </div>
    </a-modal>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

h1,
h2 {
  margin: 0;
}

p {
  margin: 6px 0 0;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
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

.file-hint {
  color: var(--color-text-2);
  font-size: var(--jl-font-base);
  font-weight: 600;
}

.match-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.match-form label {
  font-size: var(--jl-font-base);
  font-weight: 600;
  color: var(--color-text-1);
}

.hint {
  margin: 6px 0 0;
}
</style>
