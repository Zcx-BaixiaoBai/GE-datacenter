<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">集团汇总</div>
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">设备总数</div><div class="value">{{ s.total }}</div></div>
      <div class="kpi-card"><div class="label">故障设备</div><div class="value" style="color:var(--accent-red)">{{ s.fault }}</div></div>
      <div class="kpi-card"><div class="label">故障率</div><div class="value" style="color:var(--accent)">{{ (s.fault_rate*100).toFixed(1) }}%</div><div class="sub">通讯时差 ≥ 90天</div></div>
      <div class="kpi-card"><div class="label">覆盖项目</div><div class="value">{{ data.projects.length }}</div></div>
    </div>

    <div class="section-title">设备明细 ({{ data.projects.length }} 个项目)</div>
    <table class="data-table">
      <thead><tr>
        <th class="sortable" @click="sortBy('project_name')">项目名称 <span class="sort-ind">{{ sortInd('project_name') }}</span></th>
        <th class="num sortable" @click="sortBy('total')">总设备 <span class="sort-ind">{{ sortInd('total') }}</span></th>
        <th class="num sortable" @click="sortBy('fault')">故障 <span class="sort-ind">{{ sortInd('fault') }}</span></th>
        <th class="sortable" @click="sortBy('fault_rate')" style="min-width:180px">故障率 <span class="sort-ind">{{ sortInd('fault_rate') }}</span></th>
      </tr></thead>
      <tbody>
        <tr v-for="p in sortedProjects" :key="p.project_name">
          <td>{{ p.project_name }}</td>
          <td class="num">{{ p.total }}</td>
          <td class="num" :style="{color: p.fault > 0 ? 'var(--accent-red)' : ''}">{{ p.fault }}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="progress-bar" style="flex:1">
                <div class="fill" :class="p.fault_rate > 0.3 ? 'red' : p.fault_rate > 0.1 ? 'yellow' : 'green'"
                     :style="{ width: Math.min(p.fault_rate*100, 100) + '%' }"></div>
              </div>
              <span style="font-size:12px;color:var(--text-secondary);min-width:40px;text-align:right">{{ (p.fault_rate*100).toFixed(1) }}%</span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
const loading = ref(true)
const data = ref({ summary: {}, projects: [] })
const s = computed(() => data.value.summary)

const sortKey = ref('')
const sortOrder = ref(1)
function sortBy(key) {
  if (sortKey.value === key) { sortOrder.value *= -1 } else { sortKey.value = key; sortOrder.value = 1 }
}
function sortInd(key) { return sortKey.value === key ? (sortOrder.value > 0 ? '↑' : '↓') : '↕' }

const sortedProjects = computed(() => {
  const arr = data.value.projects || []
  if (!sortKey.value) return arr
  return [...arr].sort((a, b) => {
    let av = a[sortKey.value], bv = b[sortKey.value]
    if (typeof av === 'string' || typeof bv === 'string') return String(av||'').localeCompare(String(bv||'')) * sortOrder.value
    return (av - bv) * sortOrder.value
  })
})

onMounted(async () => { try { data.value = await api.getEquipment() } catch(e){} loading.value = false })
</script>

<style scoped>
.data-table th.sortable { cursor: pointer; user-select: none; }
.data-table th.sortable:hover { color: var(--accent); }
.sort-ind { font-size: 10px; opacity: 0.5; }
</style>
