<script setup lang="ts">
import { Message } from "@arco-design/web-vue"
import { computed, ref, watch } from "vue"
import { fetchStores, type RemittanceRow, type StoreSummary } from "@/api/client"
import MoneyText from "@/components/MoneyText.vue"
import { useRemittanceStore } from "@/stores/useRemittanceStore"

interface DayDraft {
  day: number
  remit: string
  ship: string
}

const props = defineProps<{
  visible: boolean
  row: RemittanceRow | null
  dayCount: number
}>()

const emit = defineEmits<{ close: [] }>()
const store = useRemittanceStore()
const opening = ref("")
const dayDrafts = ref<DayDraft[]>([])
const stores = ref<StoreSummary[]>([])
const targetStoreId = ref<number | undefined>(undefined)
const syncMode = ref<"one" | "all">("one")
const savingDay = ref<number | null>(null)

const storeOptions = computed(() => stores.value.map((item) => ({ value: item.id, label: item.displayName })))

watch(
  () => props.row,
  (row) => {
    if (row === null) {
      dayDrafts.value = []
      return
    }
    opening.value = row.openingBalance
    targetStoreId.value = row.storeId
    dayDrafts.value = Array.from({ length: props.dayCount }, (_, index) => {
      const day = index + 1
      const cell = row.cells[String(day)]
      return {
        day,
        remit: cell?.remit ?? "",
        ship: cell?.ship ?? "",
      }
    })
  },
  { immediate: true },
)

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      void fetchStores("").then((rows) => {
        stores.value = rows
      })
    }
  },
)

function originalCell(day: number, kind: "remit" | "ship"): string {
  if (props.row === null) {
    return ""
  }
  const cell = props.row.cells[String(day)]
  return (kind === "remit" ? cell?.remit : cell?.ship) ?? ""
}

async function saveOpening(): Promise<void> {
  if (props.row === null) {
    return
  }
  try {
    await store.saveOpening(props.row.id, opening.value)
    Message.success("上月余额已保存")
  } catch {
    Message.error(store.errorMessage || "保存失败")
  }
}

async function saveDayField(day: number, kind: "remit" | "ship"): Promise<void> {
  if (props.row === null) {
    return
  }
  const draft = dayDrafts.value.find((item) => item.day === day)
  if (draft === undefined) {
    return
  }
  const next = (kind === "remit" ? draft.remit : draft.ship).trim()
  const previous = originalCell(day, kind)
  if (next === previous) {
    return
  }
  savingDay.value = day
  try {
    await store.saveCell(props.row.id, day, kind, next === "" ? null : next)
    Message.success(`${day}日${kind === "remit" ? "汇款" : "发货"}已保存`)
  } catch {
    // 回滚草稿到原值，避免界面和库不一致
    if (kind === "remit") {
      draft.remit = previous
    } else {
      draft.ship = previous
    }
    Message.error(store.errorMessage || "保存失败")
  } finally {
    savingDay.value = null
  }
}

async function reassign(): Promise<void> {
  if (props.row === null || targetStoreId.value === undefined) {
    return
  }
  try {
    await store.reassignRow(props.row.id, targetStoreId.value, syncMode.value)
    Message.success(syncMode.value === "one" ? "已改挂这一行" : "已同步该原始名称下全部汇款行")
    emit("close")
  } catch {
    Message.error(store.errorMessage || "改挂失败")
  }
}
</script>

<template>
  <a-drawer :visible="visible" :width="720" title="编辑汇款行" unmount-on-close @cancel="emit('close')">
    <template v-if="row">
      <a-alert type="info" style="margin-bottom: 16px">
        汇款月表是独立台账，不会从发货单自动覆盖。临时加货、补记汇款，直接改下面某一天的「汇款」或「发货」即可；失焦后自动保存并重算总额。
      </a-alert>
      <a-descriptions :column="1" bordered>
        <a-descriptions-item label="显示名">{{ row.displayName }}</a-descriptions-item>
        <a-descriptions-item label="原始名称">{{ row.importedRawName }}</a-descriptions-item>
        <a-descriptions-item label="汇款总额"><MoneyText :value="row.remitTotal" /></a-descriptions-item>
        <a-descriptions-item label="发货总额"><MoneyText :value="row.shipTotal" /></a-descriptions-item>
        <a-descriptions-item label="余额"><MoneyText :value="row.balance" /></a-descriptions-item>
      </a-descriptions>

      <h3>上月余额</h3>
      <div class="row">
        <a-input v-model="opening" />
        <a-button type="primary" :loading="store.saving" @click="saveOpening">保存</a-button>
      </div>

      <h3>按日金额（可手改）</h3>
      <div class="day-table">
        <div class="day-head">
          <span>日</span>
          <span>汇款</span>
          <span>发货</span>
        </div>
        <div v-for="item in dayDrafts" :key="item.day" class="day-row">
          <span class="day-label">{{ item.day }}日</span>
          <a-input
            v-model="item.remit"
            placeholder="空=无"
            :disabled="savingDay === item.day"
            @blur="saveDayField(item.day, 'remit')"
            @press-enter="saveDayField(item.day, 'remit')"
          />
          <a-input
            v-model="item.ship"
            placeholder="空=无"
            :disabled="savingDay === item.day"
            @blur="saveDayField(item.day, 'ship')"
            @press-enter="saveDayField(item.day, 'ship')"
          />
        </div>
      </div>

      <h3>改挂门店</h3>
      <div class="row">
        <a-select v-model="targetStoreId" :options="storeOptions" allow-search style="flex: 1" />
        <a-select v-model="syncMode" style="width: 160px">
          <a-option value="one">只改这一行</a-option>
          <a-option value="all">同步全部</a-option>
        </a-select>
        <a-button :loading="store.saving" @click="reassign">改挂</a-button>
      </div>
    </template>
  </a-drawer>
</template>

<style scoped>
h3 {
  margin: 20px 0 10px;
  font-size: var(--jl-font-lg);
  font-weight: 700;
}

.row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.day-table {
  max-height: 480px;
  overflow: auto;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
}

.day-head,
.day-row {
  display: grid;
  grid-template-columns: 72px 1fr 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
}

.day-head {
  position: sticky;
  top: 0;
  background: var(--color-fill-2);
  font-size: var(--jl-font-base);
  font-weight: 700;
  z-index: 1;
}

.day-label {
  font-size: var(--jl-font-base);
  font-weight: 700;
}

.day-row:nth-child(even) {
  background: #fff;
}
</style>
