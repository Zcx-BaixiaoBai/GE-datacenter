<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">同步模块</div>
    <div class="sync-grid">
      <div class="sync-card" v-for="m in modules" :key="m.id">
        <div class="sync-card-header">
          <span class="sync-name">{{ m.name }}</span>
          <span class="sync-badge" :class="m.running ? 'running' : 'idle'">
            {{ m.running ? '运行中' : '空闲' }}
          </span>
        </div>
        <div class="sync-card-body">
          <div class="sync-row"><span>定时间隔</span><span>{{ m.interval_min > 0 ? m.interval_min + '分钟' : '未启用' }}</span></div>
          <div class="sync-row" v-if="m.remaining_sec >= 0"><span>下次执行</span><span>{{ m.next_run }}</span></div>
          <div class="sync-row"><span>数据文件</span><span :class="m.output_exists ? 'ok' : 'missing'">{{ m.output_exists ? '已生成' : '未生成' }}</span></div>
        </div>
        <button class="btn-ghost sync-trigger" :disabled="m.running" @click="triggerOne(m.id)">
          {{ m.running ? '采集中...' : '立即采集' }}
        </button>
      </div>
    </div>

    <div class="section-title" style="margin-top:24px">调度控制</div>
    <div class="scheduler-bar">
      <div class="scheduler-status">
        <span class="sync-badge" :class="schedulerActive ? 'running' : 'idle'">{{ schedulerActive ? '运行中' : '已停止' }}</span>
      </div>
      <div class="scheduler-actions">
        <button class="btn-ghost" v-if="!schedulerActive" @click="startScheduler">启动调度</button>
        <button class="btn-ghost" v-else @click="stopScheduler">停止调度</button>
        <button class="btn-ghost" @click="triggerAll" :disabled="anyRunning">全部采集</button>
      </div>
    </div>

    <div class="section-title" style="margin-top:24px">同步日志</div>
    <div class="log-panel">
      <div class="log-line" v-for="(log, i) in logs" :key="i" :class="log.type">
        <span class="log-time">{{ log.time }}</span>
        <span class="log-module">[{{ log.module }}]</span>
        <span class="log-msg">{{ log.msg }}</span>
      </div>
      <div v-if="!logs.length" class="log-empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const loading = ref(true)
const modules = ref([])
const schedulerActive = ref(false)
const logs = ref([])
let timer = null

const anyRunning = computed(() => modules.value.some(m => m.running))

async function loadStatus() {
  try {
    const d = await api.getSyncCenterStatus()
    modules.value = d.modules || []
    schedulerActive.value = d.scheduler_active
  } catch (e) {
    if (e.response?.status === 401) { loading.value = false; return }
  }
  loading.value = false
}

async function loadLogs() {
  try { logs.value = await api.getSyncLogs(50) } catch {}
}

async function triggerOne(mid) {
  try {
    await api.triggerSync(mid)
    ElMessage.success('已触发采集')
    setTimeout(loadStatus, 1000)
  } catch (e) { ElMessage.error('触发失败') }
}

async function triggerAll() {
  try {
    await api.triggerAllSync()
    ElMessage.success('已触发全部采集')
    setTimeout(loadStatus, 1000)
  } catch (e) { ElMessage.error('触发失败') }
}

async function startScheduler() {
  try { await api.startScheduler(); ElMessage.success('调度已启动'); loadStatus() } catch { ElMessage.error('启动失败') }
}

async function stopScheduler() {
  try { await api.stopScheduler(); ElMessage.success('调度已停止'); loadStatus() } catch { ElMessage.error('停止失败') }
}

onMounted(() => {
  loadStatus(); loadLogs()
  timer = setInterval(() => { loadStatus(); loadLogs() }, 5000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.sync-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
.sync-card {
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow-sm);
}
.sync-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sync-name { font-size: 14px; font-weight: 600; color: var(--text-1); }
.sync-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.sync-badge.running { background: rgba(26,127,55,.1); color: var(--green); }
.sync-badge.idle { background: var(--bg-hover); color: var(--text-3); }
.sync-card-body { margin-bottom: 12px; }
.sync-row { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; color: var(--text-2); }
.sync-row .ok { color: var(--green); }
.sync-row .missing { color: var(--text-3); }
.sync-trigger { width: 100%; justify-content: center; font-size: 12px; }
.scheduler-bar { display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 12px 16px; }
.scheduler-actions { display: flex; gap: 8px; }
.log-panel {
  background: #0d1117; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px; max-height: 400px; overflow-y: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
}
.log-line { padding: 2px 0; display: flex; gap: 8px; }
.log-time { color: #6e7681; flex-shrink: 0; }
.log-module { color: #58a6ff; flex-shrink: 0; }
.log-msg { color: #c9d1d9; }
.log-line.error .log-msg { color: #f85149; }
.log-line.success .log-msg { color: #3fb950; }
.log-empty { color: #6e7681; text-align: center; padding: 20px; }
</style>
