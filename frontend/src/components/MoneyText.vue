<script setup lang="ts">
import { computed } from "vue"
import { formatMoney } from "@/utils/format"

const props = defineProps<{ value: string | null }>()

const text = computed(() => formatMoney(props.value))
const negative = computed(() => props.value !== null && props.value.startsWith("-"))
</script>

<template>
  <span class="money" :class="{ negative }">{{ text }}</span>
</template>

<style scoped>
.money {
  font-size: var(--jl-font-base);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.negative {
  color: rgb(var(--red-6));
}
</style>
