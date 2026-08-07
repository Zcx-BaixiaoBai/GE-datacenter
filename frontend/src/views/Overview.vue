<template>
  <div class="page-container" v-loading="loading">
    <!-- KPI -->
    <div class="section-title">核心指标</div>
    <div class="kpi-grid">
      <div class="kpi-card" v-for="k in kpis" :key="k.label">
        <div class="label">{{ k.label }}</div>
        <div class="value" :style="{ color: k.color }">{{ k.value }}</div>
        <div class="sub">{{ k.sub }}</div>
      </div>
    </div>

    <!-- 图表 -->
    <div class="section-title">数据分析</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
      <div class="chart-container">
        <div class="chart-title">电表故障排名 TOP10</div>
        <div ref="chart1" style="height:280px"></div>
      </div>
      <div class="chart-container">
        <div class="chart-title">安全隐患分布</div>
        <div ref="chart2" style="height:280px"></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="chart-container">
        <div class="chart-title">设备通讯故障分布</div>
        <div ref="chart3" style="height:280px"></div>
      </div>
      <div class="chart-container">
        <div class="chart-title">板块覆盖总览</div>
        <div ref="chart4" style="height:280px"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const loading = ref(true)
const chart1 = ref(null), chart2 = ref(null), chart3 = ref(null), chart4 = ref(null)
const kpis = ref([])

const AXIS = { axisLabel: { color: '#656d76', fontSize: 11 }, splitLine: { lineStyle: { color: '#ebeef0' } }, axisLine: { lineStyle: { color: '#d0d7de' } } }

function build(s) {
  kpis.value = [
    { label: '智能电表总数', value: s.meters.total, sub: `故障 ${s.meters.fault} / 离线 ${s.meters.offline}`, color: 'var(--accent)' },
    { label: '电表故障率', value: (s.meters.fault_rate * 100).toFixed(2) + '%', sub: `${s.meters.project_count} 个项目`, color: 'var(--accent-red)' },
    { label: '隐患总数', value: s.safety.hazard_total, sub: `逾期 ${s.safety.hazard_overdue}`, color: 'var(--accent-yellow)' },
    { label: '安全履职', value: s.safety.duty_total, sub: `已逾期 ${s.safety.duty_overdue}`, color: 'var(--accent-purple)' },
    { label: '水压异常', value: s.safety.wp_low + s.safety.wp_high, sub: `失压 ${s.safety.wp_low}`, color: 'var(--accent-red)' },
    { label: '设备总数', value: s.equipment.total, sub: `故障 ${s.equipment.fault} / ${ (s.equipment.fault_rate*100).toFixed(1) }%`, color: 'var(--accent)' },
  ]
}

function chartMeter(d) {
  const top = [...d].sort((a,b) => b.fault - a.fault).slice(0, 10)
  echarts.init(chart1.value).setOption({
    backgroundColor: 'transparent', tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { bottom: 0, textStyle: { color: '#656d76', fontSize: 11 } },
    grid: { left: 8, right: 8, bottom: 40, top: 12, containLabel: true },
    xAxis: { type: 'category', data: top.map(p => p.project_name), ...AXIS, axisLabel: { ...AXIS.axisLabel, rotate: 35 } },
    yAxis: { type: 'value', ...AXIS },
    series: [
      { name: '离线', type: 'bar', stack: 't', data: top.map(p => p.offline), itemStyle: { color: '#cf222e' } },
      { name: '异常送电', type: 'bar', stack: 't', data: top.map(p => p.abnormal), itemStyle: { color: '#9a6700' } },
      { name: '无签呈', type: 'bar', stack: 't', data: top.map(p => p.unpaid), itemStyle: { color: '#8250df' } },
    ]
  })
}

function chartSafety(d) {
  const s = d.summary
  echarts.init(chart2.value).setOption({
    backgroundColor: 'transparent', tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#656d76', fontSize: 11 } },
    series: [{ type: 'pie', radius: ['38%', '62%'], center: ['50%', '42%'],
      data: [
        { value: s.overdue, name: '逾期未完成', itemStyle: { color: '#cf222e' } },
        { value: s.imminent, name: '即将逾期', itemStyle: { color: '#9a6700' } },
        { value: s.pending, name: '未完成', itemStyle: { color: '#0969da' } },
      ], label: { color: '#656d76', fontSize: 11 }, labelLine: { lineStyle: { color: '#d0d7de' } }
    }]
  })
}

function chartEquip(d) {
  const top = [...d].sort((a,b) => b.fault - a.fault).slice(0, 10)
  echarts.init(chart3.value).setOption({
    backgroundColor: 'transparent', tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 8, bottom: 40, top: 12, containLabel: true },
    xAxis: { type: 'category', data: top.map(p => p.project_name), ...AXIS, axisLabel: { ...AXIS.axisLabel, rotate: 35 } },
    yAxis: { type: 'value', ...AXIS },
    series: [
      { name: '总数', type: 'bar', data: top.map(p => p.total), itemStyle: { color: '#d0d7de' } },
      { name: '故障', type: 'bar', data: top.map(p => p.fault), itemStyle: { color: '#cf222e' } },
    ]
  })
}

function chartSummary(s) {
  echarts.init(chart4.value).setOption({
    backgroundColor: 'transparent', tooltip: {
      formatter: (p) => {
        const v = p.value
        return `电表覆盖率: ${v[0]}%<br/>安全覆盖率: ${v[1]}%<br/>设备覆盖率: ${v[2]}%<br/>电表健康率: ${v[3]}%<br/>设备健康率: ${v[4]}%`
      }
    },
    radar: {
      indicator: [
        { name: '电表覆盖率', max: 100 },
        { name: '安全覆盖率', max: 100 },
        { name: '设备覆盖率', max: 100 },
        { name: '电表健康率', max: 100 },
        { name: '设备健康率', max: 100 },
      ],
      axisName: { color: '#656d76', fontSize: 11 },
      splitLine: { lineStyle: { color: '#ebeef0' } },
      splitArea: { areaStyle: { color: ['#ffffff', '#f6f8fa'] } },
      axisLine: { lineStyle: { color: '#d0d7de' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          Math.round(s.meters.project_count / 30 * 100),
          Math.round(s.safety.project_count / 45 * 100),
          Math.round(s.equipment.project_count / 25 * 100),
          Math.round((1 - s.meters.fault_rate) * 100),
          Math.round((1 - s.equipment.fault_rate) * 100),
        ],
        areaStyle: { color: 'rgba(9,105,218,.08)' },
        lineStyle: { color: '#0969da' },
        itemStyle: { color: '#0969da' }
      }]
    }]
  })
}

onMounted(async () => {
  try {
    const [sum, m, s, e] = await Promise.all([api.getSummary(), api.getMeters(), api.getSafety(), api.getEquipment()])
    build(sum); loading.value = false; await nextTick()
    chartMeter(m.projects); chartSafety(s); chartEquip(e.projects); chartSummary(sum)
  } catch (e) { console.error(e); loading.value = false }
})
</script>
