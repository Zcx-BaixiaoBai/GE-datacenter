<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">集团汇总</div>
    <div class="kpi-grid">
      <div class="kpi-card" v-for="cat in summaryCats" :key="cat">
        <div class="label">{{ cat }}</div>
        <div class="value" style="font-size:20px">{{ fmt(getCat(cat,'yearly_usage')) }}</div>
        <div class="sub">当期 {{ fmt(getCat(cat,'current_usage')) }} | {{ getCat(cat,'yearly_rate') || '0' }}</div>
      </div>
    </div>

    <div class="section-title">预算明细</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px">
      <button v-for="cat in categories" :key="cat" class="btn-ghost" :class="{active: activeCat===cat}" style="padding:4px 12px;font-size:12px" @click="activeCat=cat">
        {{ cat }}
      </button>
    </div>

    <table class="data-table">
      <thead><tr>
        <th class="sortable" @click="sortBy('project_name')">预算单位 <span class="sort-ind">{{ sortInd('project_name') }}</span></th>
        <th class="num sortable" @click="sortBy('current_usage')">当期用量 <span class="sort-ind">{{ sortInd('current_usage') }}</span></th>
        <th>当期占比</th>
        <th class="num sortable" @click="sortBy('yearly_usage')">当年用量 <span class="sort-ind">{{ sortInd('yearly_usage') }}</span></th>
        <th class="sortable" @click="sortBy('yearly_rate')" style="min-width:200px">当年占比 <span class="sort-ind">{{ sortInd('yearly_rate') }}</span></th>
      </tr></thead>
      <tbody>
        <tr v-for="p in sortedFiltered" :key="p.project_name">
          <td>{{ p.project_name }}</td>
          <td class="num">{{ fmt(getP(p,'current_usage')) }}</td>
          <td>{{ getP(p,'current_rate') || '-' }}</td>
          <td class="num">{{ fmt(getP(p,'yearly_usage')) }}</td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="progress-bar" style="flex:1">
                <div class="fill" :class="rate(p,'yearly_rate') > 80 ? 'red' : rate(p,'yearly_rate') > 50 ? 'yellow' : 'green'"
                     :style="{ width: Math.min(rate(p,'yearly_rate'), 100) + '%' }"></div>
              </div>
              <span style="font-size:12px;color:var(--text-secondary);min-width:50px;text-align:right">{{ getP(p,'yearly_rate') || '0' }}</span>
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
const data = ref({ summary: {}, projects: [], categories: [] })
const activeCat = ref('商贸总预算')
const categories = computed(() => data.value.categories || [])
const summaryCats = computed(() => { const a = data.value.categories || []; return a.length > 6 ? a.slice(0,6) : a })
const filtered = computed(() => (data.value.projects||[]).filter(p => p.categories && p.categories[activeCat.value]))

const sortKey = ref('')
const sortOrder = ref(1)
function sortBy(key) {
  if (sortKey.value === key) { sortOrder.value *= -1 } else { sortKey.value = key; sortOrder.value = 1 }
}
function sortInd(key) { return sortKey.value === key ? (sortOrder.value > 0 ? '↑' : '↓') : '↕' }

const sortedFiltered = computed(() => {
  const arr = filtered.value
  if (!sortKey.value) return arr
  return [...arr].sort((a, b) => {
    let av, bv
    if (sortKey.value === 'project_name') {
      av = a.project_name || ''; bv = b.project_name || ''
      return av.localeCompare(bv) * sortOrder.value
    }
    // 从 category 数据里取值
    const ca = a.categories?.[activeCat.value] || {}
    const cb = b.categories?.[activeCat.value] || {}
    if (sortKey.value === 'yearly_rate') {
      av = parseFloat(String(ca.yearly_rate||'0').replace('%',''))
      bv = parseFloat(String(cb.yearly_rate||'0').replace('%',''))
    } else {
      av = Number(ca[sortKey.value] || 0)
      bv = Number(cb[sortKey.value] || 0)
    }
    return (av - bv) * sortOrder.value
  })
})

function getCat(c, f) { const s = data.value.summary; if (!s||!s.categories) return 0; const v = s.categories[c]; return v ? v[f] : 0 }
function getP(p, f) { const v = p?.categories?.[activeCat.value]; return v ? v[f] : 0 }
function rate(p, f) { const v = getP(p,f); if (!v) return 0; const n = parseFloat(String(v).replace('%','')); return isNaN(n) ? 0 : n }
function fmt(v) { if (v==null) return '-'; const n=Number(v); if(isNaN(n)) return String(v); return n>=10000 ? (n/10000).toFixed(2)+'万' : n.toFixed(2) }

onMounted(async () => { try { data.value = await api.getBudget() } catch(e){} loading.value = false })
</script>

<style scoped>
.data-table th.sortable { cursor: pointer; user-select: none; }
.data-table th.sortable:hover { color: var(--accent); }
.sort-ind { font-size: 10px; opacity: 0.5; }
</style>
