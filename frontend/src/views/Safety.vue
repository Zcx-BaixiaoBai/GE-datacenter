<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">集团汇总</div>
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">隐患总数</div><div class="value" style="color:var(--accent-yellow)">{{ hazardTotal }}</div><div class="sub">一般{{ s.hazard_general }} 严重{{ s.hazard_serious }} 重大{{ s.hazard_major }}</div></div>
      <div class="kpi-card"><div class="label">逾期未完成</div><div class="value" style="color:var(--accent-red)">{{ s.overdue }}</div></div>
      <div class="kpi-card"><div class="label">即将逾期</div><div class="value" style="color:var(--accent-yellow)">{{ s.imminent }}</div></div>
      <div class="kpi-card"><div class="label">未完成</div><div class="value" style="color:var(--accent)">{{ s.pending }}</div></div>
      <div class="kpi-card"><div class="label">安全履职</div><div class="value">{{ dutyTotal }}</div><div class="sub">完成{{ s.duty_completed }} 已逾期{{ s.duty_overdue }}</div></div>
      <div class="kpi-card"><div class="label">水压异常</div><div class="value" style="color:var(--accent-red)">{{ s.wp_low + s.wp_high }}</div><div class="sub">失压{{ s.wp_low }} 超压{{ s.wp_high }}</div></div>
    </div>

    <div class="section-title">隐患核查 ({{ data.projects.length }} 个项目)</div>
    <table class="data-table">
      <thead><tr>
        <th class="sortable" rowspan="2" @click="sortBy('project_name')">项目名称 <span class="sort-ind">{{ sortInd('project_name') }}</span></th>
        <th colspan="3" style="text-align:center">隐患级别(当月)</th>
        <th colspan="3" style="text-align:center">整改进度</th>
        <th colspan="3" style="text-align:center">安全履职(当月)</th>
        <th colspan="3" style="text-align:center">水压设备</th>
      </tr><tr>
        <th class="num sortable" @click="sortBy('hazard_general')">一般 <span class="sort-ind">{{ sortInd('hazard_general') }}</span></th>
        <th class="num sortable" @click="sortBy('hazard_serious')">严重 <span class="sort-ind">{{ sortInd('hazard_serious') }}</span></th>
        <th class="num sortable" @click="sortBy('hazard_major')">重大 <span class="sort-ind">{{ sortInd('hazard_major') }}</span></th>
        <th class="num sortable" @click="sortBy('overdue')">逾期 <span class="sort-ind">{{ sortInd('overdue') }}</span></th>
        <th class="num sortable" @click="sortBy('imminent')">即将逾期 <span class="sort-ind">{{ sortInd('imminent') }}</span></th>
        <th class="num sortable" @click="sortBy('pending')">未完成 <span class="sort-ind">{{ sortInd('pending') }}</span></th>
        <th class="num sortable" @click="sortBy('duty_completed')">已完成 <span class="sort-ind">{{ sortInd('duty_completed') }}</span></th>
        <th class="num sortable" @click="sortBy('duty_started')">已开始 <span class="sort-ind">{{ sortInd('duty_started') }}</span></th>
        <th class="num sortable" @click="sortBy('duty_overdue')">已逾期 <span class="sort-ind">{{ sortInd('duty_overdue') }}</span></th>
        <th class="num sortable" @click="sortBy('wp_low')">失压 <span class="sort-ind">{{ sortInd('wp_low') }}</span></th>
        <th class="num sortable" @click="sortBy('wp_high')">超压 <span class="sort-ind">{{ sortInd('wp_high') }}</span></th>
        <th class="num sortable" @click="sortBy('wp_offline')">离线 <span class="sort-ind">{{ sortInd('wp_offline') }}</span></th>
      </tr></thead>
      <tbody>
        <tr v-for="p in sortedProjects" :key="p.project_name">
          <td>{{ p.project_name }}</td>
          <td class="num">{{ p.hazard_general }}</td><td class="num">{{ p.hazard_serious }}</td><td class="num" :style="{color: p.hazard_major > 0 ? 'var(--accent-red)' : ''}">{{ p.hazard_major }}</td>
          <td class="num" :style="{color: p.overdue > 0 ? 'var(--accent-red)' : ''}">{{ p.overdue }}</td>
          <td class="num" :style="{color: p.imminent > 0 ? 'var(--accent-yellow)' : ''}">{{ p.imminent }}</td>
          <td class="num">{{ p.pending }}</td>
          <td class="num">{{ p.duty_completed }}</td><td class="num">{{ p.duty_started }}</td>
          <td class="num" :style="{color: p.duty_overdue > 0 ? 'var(--accent-red)' : ''}">{{ p.duty_overdue }}</td>
          <td class="num" :style="{color: p.wp_low > 0 ? 'var(--accent-red)' : ''}">{{ p.wp_low }}</td>
          <td class="num">{{ p.wp_high }}</td><td class="num">{{ p.wp_offline }}</td>
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
const hazardTotal = computed(() => { const s = data.value.summary; return (s.hazard_general||0)+(s.hazard_serious||0)+(s.hazard_major||0) })
const dutyTotal = computed(() => { const s = data.value.summary; return (s.duty_completed||0)+(s.duty_overdue_done||0)+(s.duty_started||0)+(s.duty_overdue||0)+(s.duty_reporting||0) })

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

onMounted(async () => { try { data.value = await api.getSafety() } catch(e){} loading.value = false })
</script>

<style scoped>
.data-table th.sortable { cursor: pointer; user-select: none; }
.data-table th.sortable:hover { color: var(--accent); }
.sort-ind { font-size: 10px; opacity: 0.5; }
.data-table th[rowspan] { vertical-align: bottom; }
.data-table th[colspan] { text-align: center; border-bottom: 1px solid var(--border-subtle); }
</style>
