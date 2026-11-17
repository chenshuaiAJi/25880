<script setup lang="ts">
import type { TableColumnData } from "@arco-design/web-vue/es/table/interface"
import type { RequestOption, UploadRequest } from "@arco-design/web-vue/es/upload/interfaces"
import { Message, Modal } from "@arco-design/web-vue"
import { computed, onMounted, onUnmounted, ref } from "vue"
import {
  fetchConflicts,
  fetchImportStatus,
  fetchStats,
  fetchSystem,
  fetchWarnings,
  startImport,
  uploadImportFiles,
  type ConflictItem,
  type ImportStatus,
  type LedgerStats,
  type WarningItem,
} from "@/api/client"
import { batchLabel } from "@/utils/format"

const systemRoot = ref("")
const version = ref("")
const stats = ref<LedgerStats | null>(null)
const job = ref<ImportStatus | null>(null)
const conflicts = ref<ConflictItem[]>([])
const conflictTotal = ref(0)
const conflictPage = ref(1)
const warnings = ref<WarningItem[]>([])
const warningTotal = ref(0)
const warningPage = ref(1)
const errorMessage = ref("")
const pageSize = 20
let pollTimer: ReturnType<typeof setTimeout> | undefined

const kind = ref<"remittance" | "shipment">("remittance")
const year = ref(2026)
const month = ref(1)
const mode = ref<"skip" | "replace">("skip")
const pendingFiles = ref<File[]>([])
const uploading = ref(false)

const progressRatio = computed(() => {
  if (job.value === null || job.value.filesTotal === 0) {
    return 0
  }
  return job.value.filesDone / job.value.filesTotal
})

const running = computed(() => job.value?.status === "running" || uploading.value)

const statusText = computed(() => {
  const status = job.value?.status
  if (uploading.value) {
    return "正在上传"
  }
  if (status === "running") {
    return "正在导入"
  }
  if (status === "done") {
    return "导入完成"
  }
  if (status === "error") {
    return "导入失败"
  }
  return "尚未开始"
})

const fileNames = computed(() => pendingFiles.value.map((file) => file.name).join("、"))

const monthOptions = computed(() =>
  Array.from({ length: 12 }, (_, index) => ({
    value: index + 1,
    label: `${index + 1}月`,
  })),
)

const conflictRows = computed(() =>
  conflicts.value.map((item) => ({
    ...item,
    batchLabel: batchLabel(item.batchNo, item.batchLabel),
  })),
)

const conflictColumns: TableColumnData[] = [
  { title: "业务日", dataIndex: "bizDate", width: 120 },
  { title: "文件", dataIndex: "fileName", width: 140 },
  { title: "批次", dataIndex: "batchLabel", width: 90 },
  { title: "单元格日期", dataIndex: "parsedCellDate", width: 130 },
  { title: "单元格原文", dataIndex: "cellText" },
]

const warningColumns: TableColumnData[] = [
  { title: "文件", dataIndex: "fileName", width: 180 },
  { title: "代码", dataIndex: "code", width: 180 },
  { title: "说明", dataIndex: "message" },
]

onMounted(() => {
  void refreshQuiet()
})

onUnmounted(() => {
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer)
  }
})

async function refreshQuiet(): Promise<void> {
  errorMessage.value = ""
  try {
    const [system, ledger, status] = await Promise.all([fetchSystem(), fetchStats(), fetchImportStatus()])
    systemRoot.value = system.dataRoot
    version.value = system.version
    stats.value = ledger
    job.value = status
    await loadIssues()
    if (status.status === "running") {
      schedulePoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "加载导入页失败"
  }
}

async function loadIssues(): Promise<void> {
  const [conflictPageData, warningPageData] = await Promise.all([
    fetchConflicts(conflictPage.value, pageSize),
    fetchWarnings(warningPage.value, pageSize),
  ])
  conflicts.value = conflictPageData.items
  conflictTotal.value = conflictPageData.total
  warnings.value = warningPageData.items
  warningTotal.value = warningPageData.total
}

function beforeUpload(file: File): boolean {
  if (!file.name.toLowerCase().endsWith(".xls")) {
    Message.warning("发货单/汇款明细目前只支持 .xls")
    return false
  }
  return true
}

function customSelect(option: RequestOption): UploadRequest {
  const file = option.fileItem.file
  if (file instanceof File) {
    const exists = pendingFiles.value.some((item) => item.name === file.name && item.size === file.size)
    if (!exists) {
      pendingFiles.value = [...pendingFiles.value, file]
    }
    option.onSuccess()
  } else {
    option.onError(new Error("请选择本地文件"))
  }
  return {}
}

function clearFiles(): void {
  pendingFiles.value = []
}

async function submitUpload(): Promise<void> {
  if (pendingFiles.value.length === 0) {
    Message.warning("请先选择本地 Excel 文件")
    return
  }
  if (mode.value === "replace") {
    Modal.confirm({
      title: "按 Excel 覆盖导入",
      content: "同名已导入文件会按 Excel 重新写入。系统里以后改过的金额，会被这份表盖掉。",
      onOk: () => doUpload(),
    })
    return
  }
  await doUpload()
}

async function doUpload(): Promise<void> {
  errorMessage.value = ""
  uploading.value = true
  try {
    job.value = await uploadImportFiles({
      kind: kind.value,
      year: year.value,
      month: kind.value === "shipment" ? month.value : undefined,
      mode: mode.value,
      files: pendingFiles.value,
    })
    Message.success(`已开始导入 ${pendingFiles.value.length} 个文件`)
    pendingFiles.value = []
    schedulePoll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "上传导入失败"
  } finally {
    uploading.value = false
  }
}

async function beginDirectory(nextMode: "skip" | "replace"): Promise<void> {
  errorMessage.value = ""
  try {
    job.value = await startImport(nextMode)
    schedulePoll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "启动目录导入失败"
  }
}

function confirmDirectoryReplace(): void {
  Modal.confirm({
    title: "从资料目录重新导入",
    content: "会扫描资料目录下全部发货单/汇款表。已导入文件按 Excel 覆盖，系统里改过的金额会被盖掉。",
    onOk: () => beginDirectory("replace"),
  })
}

function schedulePoll(): void {
  if (pollTimer !== undefined) {
    clearTimeout(pollTimer)
  }
  pollTimer = setTimeout(() => {
    void poll()
  }, 1000)
}

async function poll(): Promise<void> {
  try {
    const status = await fetchImportStatus()
    job.value = status
    if (status.status === "running") {
      schedulePoll()
      return
    }
    stats.value = await fetchStats()
    conflictPage.value = 1
    warningPage.value = 1
    await loadIssues()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "查询导入进度失败"
  }
}

async function onConflictPage(page: number): Promise<void> {
  conflictPage.value = page
  const data = await fetchConflicts(page, pageSize)
  conflicts.value = data.items
  conflictTotal.value = data.total
}

async function onWarningPage(page: number): Promise<void> {
  warningPage.value = page
  const data = await fetchWarnings(page, pageSize)
  warnings.value = data.items
  warningTotal.value = data.total
}
</script>

<template>
  <section class="page">
    <header>
      <h1>导入</h1>
      <p>手动选择本地 Excel 上传导入。只读不写回原文件，保存后的账以数据库为准。</p>
    </header>
    <a-alert v-if="errorMessage" type="error">{{ errorMessage }}</a-alert>

    <div class="panel">
      <h2>本地文件导入</h2>
      <div class="toolbar">
        <a-radio-group v-model="kind" type="button" :disabled="running">
          <a-radio value="remittance">汇款明细</a-radio>
          <a-radio value="shipment">发货单</a-radio>
        </a-radio-group>
        <a-input-number v-model="year" :min="2020" :max="2100" :disabled="running" />
        <a-select
          v-if="kind === 'shipment'"
          v-model="month"
          :options="monthOptions"
          :disabled="running"
          style="width: 120px"
        />
        <a-select
          v-model="mode"
          :disabled="running"
          style="width: 180px"
          :options="[
            { value: 'skip', label: '跳过已导入' },
            { value: 'replace', label: '覆盖已导入' },
          ]"
        />
      </div>
      <p class="hint">
        汇款明细文件名如「11月汇款明细总.xls」；发货单文件名如「15-16.xls」「1-2 (1).xls」，并选择对应月份。
      </p>
      <div class="toolbar">
        <a-upload
          :custom-request="customSelect"
          :show-file-list="false"
          accept=".xls,application/vnd.ms-excel"
          multiple
          :disabled="running"
          :before-upload="beforeUpload"
        >
          <template #upload-button>
            <a-button type="outline" :disabled="running">选择本地 .xls</a-button>
          </template>
        </a-upload>
        <a-button type="primary" :loading="running" @click="submitUpload">开始导入</a-button>
        <a-button :disabled="running || pendingFiles.length === 0" @click="clearFiles">清空已选</a-button>
      </div>
      <p v-if="pendingFiles.length > 0" class="hint">已选 {{ pendingFiles.length }} 个：{{ fileNames }}</p>
    </div>

    <div class="panel">
      <p class="path">资料留存目录：{{ systemRoot }}</p>
      <p class="path">版本 {{ version }} · 本机 http://127.0.0.1:8787</p>
      <div class="progress">
        <span>{{ statusText }}</span>
        <a-progress :percent="progressRatio" />
        <span v-if="job">{{ job.filesDone }} / {{ job.filesTotal }} {{ job.currentFile }}</span>
      </div>
      <div v-if="job && job.status !== 'idle'" class="stats">
        <span>汇款表 {{ job.result.remittanceFiles }}</span>
        <span>发货单文件 {{ job.result.shipmentFiles }}</span>
        <span>跳过 {{ job.result.skippedFiles }}</span>
        <span>失败 {{ job.result.failedFiles }}</span>
        <span>订单 {{ job.result.orders }}</span>
        <span>新建门店 {{ job.result.storesCreated }}</span>
        <span>日期冲突 {{ job.result.conflicts }}</span>
      </div>
      <a-alert v-if="job?.error" type="error">{{ job.error }}</a-alert>
      <ul v-if="job && job.result.failures.length > 0" class="failures">
        <li v-for="item in job.result.failures" :key="item.file">{{ item.file }}：{{ item.message }}</li>
      </ul>
      <div class="toolbar secondary">
        <span class="hint">可选：仍可从资料目录整批扫描</span>
        <a-button :disabled="running" @click="beginDirectory('skip')">目录导入新文件</a-button>
        <a-button :disabled="running" @click="confirmDirectoryReplace">目录重新导入</a-button>
      </div>
    </div>

    <div v-if="stats" class="stats">
      <span>门店 {{ stats.stores }}</span>
      <span>发货订单 {{ stats.orders }}</span>
      <span>商品行 {{ stats.lines }}</span>
      <span>汇款月表 {{ stats.sheets }}</span>
      <span>日期冲突 {{ stats.conflicts }}</span>
      <span>导入提示 {{ stats.warnings }}</span>
    </div>
    <div class="panel">
      <h2>日期冲突</h2>
      <p>单元格里的发货日期和文件名不一致。入账仍按文件名，这里只列出来。</p>
      <a-table :columns="conflictColumns" :data="conflictRows" :pagination="false" row-key="id" />
      <div class="pager">
        <a-pagination :current="conflictPage" :page-size="pageSize" :total="conflictTotal" @change="onConflictPage" />
      </div>
    </div>
    <div class="panel">
      <h2>导入提示</h2>
      <a-table :columns="warningColumns" :data="warnings" :pagination="false" row-key="id" />
      <div class="pager">
        <a-pagination :current="warningPage" :page-size="pageSize" :total="warningTotal" @change="onWarningPage" />
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

h1,
h2 {
  margin: 0;
}

p {
  margin: 6px 0 0;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 18px;
}

.path {
  margin: 0 0 8px;
}

.toolbar,
.stats,
.progress {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 12px;
}

.toolbar.secondary {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-2);
}

.hint {
  margin: 8px 0 0;
}

.progress {
  max-width: 720px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.failures {
  margin: 12px 0 0;
  color: rgb(var(--red-6));
}
</style>
