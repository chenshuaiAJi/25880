<script setup lang="ts">
import { IconBook, IconCalendar, IconFile, IconImport, IconStorage } from "@arco-design/web-vue/es/icon"
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

const route = useRoute()
const router = useRouter()

const selectedKeys = computed(() => {
  if (route.path.startsWith("/shipments")) {
    return ["/shipments"]
  }
  if (route.path.startsWith("/stores")) {
    return ["/stores"]
  }
  if (route.path.startsWith("/import")) {
    return ["/import"]
  }
  if (route.path.startsWith("/bank")) {
    return ["/bank"]
  }
  return ["/remittances"]
})

function openMenu(key: string): void {
  void router.push(key)
}
</script>

<template>
  <a-layout class="shell">
    <a-layout-sider class="sider" :width="248">
      <div class="brand">
        <strong>门店对账</strong>
        <span>赣榆鲜品市场 · 大字版</span>
      </div>
      <a-menu :selected-keys="selectedKeys" @menu-item-click="openMenu">
        <a-menu-item key="/remittances">
          <template #icon><IconCalendar /></template>
          汇款月表
        </a-menu-item>
        <a-menu-item key="/shipments">
          <template #icon><IconFile /></template>
          发货单
        </a-menu-item>
        <a-menu-item key="/stores">
          <template #icon><IconStorage /></template>
          门店
        </a-menu-item>
        <a-menu-item key="/import">
          <template #icon><IconImport /></template>
          导入
        </a-menu-item>
        <a-menu-item key="/bank">
          <template #icon><IconBook /></template>
          银行流水
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}

.shell :deep(.arco-layout) {
  min-width: 0;
}

.sider {
  background: #fff;
  border-right: 1px solid var(--color-border-2);
}

.sider :deep(.arco-menu) {
  padding: 8px 10px 16px;
  background: transparent;
}

.sider :deep(.arco-menu-item) {
  font-weight: 600;
}

.brand {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 24px 18px 16px;
}

.brand strong {
  font-size: var(--jl-font-xl);
  line-height: 1.3;
  letter-spacing: 0.02em;
}

.brand span {
  color: var(--color-text-2);
  font-size: var(--jl-font-sm);
  font-weight: 600;
}

.content {
  min-width: 0;
  padding: var(--jl-page-pad);
  background: var(--color-fill-2);
}
</style>
