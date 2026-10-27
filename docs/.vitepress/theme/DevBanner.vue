<script setup lang="ts">
import { useData, useRoute } from 'vitepress'

const { site } = useData()
const route = useRoute()
</script>

<template>
  <div v-if="site.base === '/dev/'" class="dev-banner">
    Development docs for the next release, built from <code>develop</code>.
    <a :href="'/' + route.path.slice(site.base.length)" target="_self">Switch to production</a>
  </div>
</template>

<style scoped>
/* The height matches --vp-layout-top-height, which config.mts sets for development builds. */
.dev-banner {
  position: fixed;
  top: 0;
  z-index: var(--vp-z-index-layout-top);
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 40px;
  padding: 0 16px;
  background-color: var(--vp-c-warning-soft);
  color: var(--vp-c-text-1);
  font-size: 13px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dev-banner a {
  color: var(--vp-c-brand-1);
  font-weight: 500;
}
</style>
