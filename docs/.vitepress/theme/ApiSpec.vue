<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useData } from 'vitepress'

// pages.yml writes the spec of each branch to <base>openapi.json (scripts/export_openapi.py).
// Bruno fetches it by absolute URL, so it's built from the address the page was loaded from:
// production, /dev/ or a local preview alike. The production address covers the server render.
const { site } = useData()
const origin = ref('https://statora.timothestoifl24.dev')
onMounted(() => (origin.value = location.origin))

const spec = () => `${origin.value}${site.value.base}openapi.json`
const bruno = () => `https://fetch.usebruno.com?url=${encodeURIComponent(spec())}&type=openapi`
</script>

<template>
  <div class="api-spec">
    <a :href="bruno()" target="_blank" rel="noopener noreferrer" class="bruno">
      <img src="https://fetch.usebruno.com/button.svg" alt="Fetch in Bruno" width="130" height="30" />
    </a>
    <a :href="spec()" target="_blank" rel="noopener" class="download">OpenAPI spec (JSON)</a>
  </div>
</template>

<style scoped>
.api-spec {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  align-items: center;
  margin: 20px 0;
}
.bruno { display: inline-flex; }
.bruno img { display: block; }
.download { font-weight: 500; }
</style>
