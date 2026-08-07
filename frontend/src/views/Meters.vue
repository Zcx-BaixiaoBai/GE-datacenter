<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">集团汇总</div>
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">总表具</div><div class="value">{{ s.total }}</div></div>
      <div class="kpi-card"><div class="label">故障电表</div><div class="value" style="color:var(--accent-red)">{{ s.fault }}</div></div>
      <div class="kpi-card"><div class="label">离线</div><div class="value" style="color:var(--accent-red)">{{ s.offline }}</div></div>
      <div class="kpi-card"><div class="label">异常送电</div><div class="value" style="color:var(--accent-yellow)">{{ s.abnormal }}</div></div>
      <div class="kpi-card"><div class="label">无签呈后付费</div><div class="value" style="color:var(--accent-purple)">{{ s.unpaid }}</div></div>
      <div class="kpi-card"><div class="label">平均故障率</div><div class="value" style="color:var(--accent)">{{ (data.avg_fault_rate*100).toFixed(2) }}%</div></div>
    </div>

    <div class="section-title">项目明细 ({{ data.projects.length }})</div>
    <table class="data-table">
      <thead><tr>
        <th class="sortable" @click="sortBy('rank')">排名 <span class="sort-ind">{{ sortInd('rank') }}</span></th>
        <th class="sortable" @click="sortBy('project_name')">项目名称 <span class="sort-ind">{{ sortInd('project_name') }}</span></th>
        <th class="sortable" @click="sortBy('pm_name')">负责人 <span class="sort-ind">{{ sortInd('pm_name') }}</span></th>
        <th class="sortable" @click="sortBy('eng_name')">工程负责人 <span class="sort-ind">{{ sortInd('eng_name') }}</span></th>
        <th class="num sortable" @click="sortBy('total')">总表具 <span class="sort-ind">{{ sortInd('total') }}</span></th>
        <th class="num sortable" @click="sortBy('fault')">故障 <span class="sort-ind">{{ sortInd('fault') }}</span></th>
        <th class="num sortable" @click="sortBy('fault_rate')">故障率 <span class="sort-ind">{{ sortInd('fault_rate') }}</span></th>
        <th class="num sortable" @click="sortBy('offline')">离线 <span class="sort-ind">{{ sortInd('offline') }}</span></th>
        <th class="num sortable" @click="sortBy('abnormal')">异常送电 <span class="sort-ind">{{ sortInd('abnormal') }}</span></th>
        <th class="num sortable" @click="sortBy('unpaid')">无签呈 <span class="sort-ind">{{ sortInd('unpaid') }}</span></th>
        <th class="sortable" @click="sortBy('evaluation')">评价 <span class="sort-ind">{{ sortInd('evaluation') }}</span></th>
      </tr></thead>
      <tbody>
        <tr v-for="p in sortedProjects" :key="p.project_name">
          <td>{{ p.rank }}</td>
          <td>{{ p.project_name }}</td>
          <td>{{ p.pm_name || '-' }}</td>
          <td>{{ p.eng_name || '-' }}</td>
          <td class="num">{{ p.total }}</td>
          <td class="num" :style="{ color: p.fault > 0 ? 'var(--accent-red)' : '' }">{{ p.fault }}</td>
          <td class="num" :style="{ color: p.fault_rate > data.avg_fault_rate ? 'var(--accent-red)' : '' }">{{ (p.fault_rate*100).toFixed(2) }}%</td>
          <td class="num">{{ p.offline }}</td>
          <td class="num">{{ p.abnormal }}</td>
          <td class="num">{{ p.unpaid }}</td>
          <td><span class="status-tag" :class="p.evaluation === '优' ? 'good' : p.evaluation === '良' ? 'warn' : 'bad'">{{ p.evaluation }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
const loading = ref(true)
const data = ref({ summary: {}, projects: [], avg_fault_rate: 0 })
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

onMounted(async () => { try { data.value = await api.getMeters() } catch(e){} loading.value = false })
</script>

<style scoped>
.data-table th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
.data-table th.sortable:hover { color: var(--accent); }
.sort-ind { font-size: 10px; opacity: 0.5; }
</style>
