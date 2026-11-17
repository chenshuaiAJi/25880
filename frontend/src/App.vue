<script setup lang="ts">
import zhCN from "@arco-design/web-vue/es/locale/lang/zh-cn"
</script>

<template>
  <a-config-provider :locale="zhCN" size="large">
    <router-view />
  </a-config-provider>
</template>
