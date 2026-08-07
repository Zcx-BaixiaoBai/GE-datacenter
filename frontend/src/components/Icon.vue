<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" :stroke-width="strokeWidth"
    stroke-linecap="round" stroke-linejoin="round"
    class="icon"
  >
    <component :is="paths" />
  </svg>
</template>

<script setup>
import { computed, h } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 18 },
  strokeWidth: { type: Number, default: 1.8 }
})

const ICON_PATHS = {
  dashboard: 'M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z',
  zap: 'M13 2L3 14h7l-1 8 10-12h-7z',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  cpu: 'M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2M6 6h12v12H6zM9 9h6v6H9z',
  budget: 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
  refresh: 'M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5',
  alert: 'M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  activity: 'M22 12h-4l-3 9L9 3l-3 9H2',
  chevron: 'M9 18l6-6-6-6',
  check: 'M20 6L9 17l-5-5',
  x: 'M18 6L6 18M6 6l12 12',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  filter: 'M22 3H2l8 9.5V19l4 2v-8.5L22 3z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
  server: 'M2 8h20v8H2zM2 16h20v4H2zM6 12h.01M10 12h.01',
}

const paths = computed(() => {
  const d = ICON_PATHS[props.name] || ''
  return h('path', { d })
})
</script>

<style scoped>
.icon { display: inline-block; vertical-align: middle; flex-shrink: 0; }
</style>
