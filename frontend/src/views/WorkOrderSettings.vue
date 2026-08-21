<template>
  <div class="page-container" v-loading="loading">
    <div class="section-title">工单推送配置</div>
    <div class="cfg-card">
      <div class="cfg-row">
        <label class="cfg-label">启用每周定时</label>
        <input type="checkbox" v-model="cfg.enabled" class="cfg-check" />
        <span class="cfg-hint">关闭后调度器不自动触发（仍可手动「立即推送全部」）</span>
      </div>
      <div class="cfg-row">
        <label class="cfg-label">推送时间</label>
        <select v-model.number="cfg.weekly_day" class="cfg-select">
          <option v-for="(n, i) in weekdayNames" :key="i" :value="i + 1">{{ n }}</option>
        </select>
        <input type="time" v-model="cfg.weekly_time" class="cfg-time" />
        <span class="cfg-hint">与日报(每天09:00)独立，互不影响</span>
      </div>
      <div class="cfg-row">
        <label class="cfg-label">报修人电话</label>
        <input type="text" v-model="phoneInput" class="cfg-input" placeholder="统一服务号，如 13800138000" maxlength="11" />
        <span class="cfg-hint">{{ phoneMasked ? '当前已设置：' + phoneMasked + '（留空保存则不变）' : '未设置，推送将跳过' }}</span>
      </div>
      <div class="cfg-actions">
        <button class="btn-ghost" @click="saveConfig">保存配置</button>
        <span class="cfg-hint" v-if="status.creater_phone_set === false && cfg.enabled" style="color:var(--red)">
          ⚠ 已启用但未填电话，将无法推送
        </span>
      </div>
    </div>

    <div class="section-title" style="margin-top:24px">调度控制</div>
    <div class="scheduler-bar">
      <div class="scheduler-status">
        <span class="sync-badge" :class="schedulerActive ? 'running' : 'idle'">{{ schedulerActive ? '运行中' : '已停止' }}</span>
        <span class="cfg-hint" style="margin-left:10px">
          {{ status.mapped_count || 0 }}/{{ status.project_count || 0 }} 项目已配映射
          <span v-if="status.unmapped && status.unmapped.length" style="color:var(--red)">（{{ status.unmapped.length }} 个未配）</span>
        </span>
      </div>
      <div class="scheduler-actions">
        <button class="btn-ghost" v-if="!schedulerActive" @click="startScheduler">启动调度</button>
        <button class="btn-ghost" v-else @click="stopScheduler">停止调度</button>
        <button class="btn-ghost" @click="triggerAll" :disabled="triggering">
          {{ triggering ? '推送中...' : '立即推送全部' }}
        </button>
      </div>
    </div>
    <div class="warn-banner">
      ⚠ 「立即推送全部」与「测试」都会向生产 PMS 工单系统真实创建工单（不可逆）。首次请先用「测试」对单个项目验证。
    </div>

    <div class="section-title" style="margin-top:24px">
      项目链接与名称映射
      <button class="btn-ghost" style="margin-left:12px" @click="refreshLinks" :disabled="refreshing">
        <Icon name="refresh" :size="13" /> {{ refreshing ? '刷新中...' : '刷新链接' }}
      </button>
      <button class="btn-ghost" style="margin-left:8px" @click="saveMapping">保存映射</button>
    </div>
    <div class="map-table">
      <div class="map-row map-head">
        <span>PMS项目(prj)</span>
        <span>counter_id</span>
        <span>系统项目名（映射，可编辑）</span>
        <span>启用</span>
        <span>操作</span>
      </div>
      <div class="map-row" v-for="prj in linkKeys" :key="prj"
           :class="{ unmapped: !mapping[prj] }">
        <span class="map-prj">{{ prj }}</span>
        <span class="map-cid">{{ links[prj]?.counter_id || '—' }}</span>
        <select v-model="mapping[prj]" class="map-input">
          <option value="">— 未配 —</option>
          <option v-for="n in projectOptions" :key="n" :value="n">{{ n }}</option>
        </select>
        <input type="checkbox" v-model="projectEnabled[prj]" class="cfg-check" />
        <span class="map-actions">
          <button class="btn-ghost" @click="preview(prj)" :disabled="!mapping[prj]">预览</button>
          <button class="btn-ghost" @click="testOne(prj)">测试</button>
        </span>
      </div>
    </div>

    <div class="section-title" style="margin-top:24px">推送日志</div>
    <div class="log-panel">
      <div class="log-line" v-for="(log, i) in logs" :key="i" :class="log.status">
        <span class="log-time">{{ log.date }} {{ log.time }}</span>
        <span class="log-module">[{{ log.project }}]</span>
        <span class="log-msg">{{ log.msg }}</span>
      </div>
      <div v-if="!logs.length" class="log-empty">暂无日志</div>
    </div>

    <!-- 预览弹窗 -->
    <div class="preview-mask" v-if="previewData" @click.self="previewData = null">
      <div class="preview-dialog">
        <div class="preview-head">
          <span>工单内容预览 — {{ previewPrj }}</span>
          <button class="btn-ghost" @click="previewData = null">关闭</button>
        </div>
        <div class="preview-meta">
          类型：{{ previewData.wy_type_name }} ｜ 故障：
          电表{{ previewData.counts?.meters }} / 安全{{ previewData.counts?.safety }} /
          履职{{ previewData.counts?.duty }} / 水压{{ previewData.counts?.water }} / 设备{{ previewData.counts?.equipment }}
        </div>
        <pre class="preview-content">{{ previewData.q_content }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Icon from '../components/Icon.vue'
import api from '../api'

const loading = ref(true)
const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const cfg = reactive({ enabled: false, weekly_day: 1, weekly_time: '09:00', pms_api: '', projects: {} })
const phoneInput = ref('')
const phoneMasked = ref('')
const status = reactive({ creater_phone_set: false, project_count: 0, mapped_count: 0, unmapped: [] })
const links = ref({})
const mapping = reactive({})
const projectOptions = ref([])
const projectEnabled = reactive({})
const schedulerActive = ref(false)
const logs = ref([])
const triggering = ref(false)
const refreshing = ref(false)
const previewData = ref(null)
const previewPrj = ref('')
let timer = null

const linkKeys = computed(() => Object.keys(links.value))

async function loadAll() {
  try {
    const [c, l, m, s] = await Promise.all([
      api.getWorkOrderConfig(), api.getWorkOrderLinks(),
      api.getWorkOrderMapping(), api.getWorkOrderStatus(),
    ])
    Object.assign(cfg, { enabled: !!c.enabled, weekly_day: c.weekly_day || 1, weekly_time: c.weekly_time || '09:00', pms_api: c.pms_api, projects: c.projects || {} })
    phoneMasked.value = c.creater_phone_masked || ''
    phoneInput.value = ''
    links.value = l || {}
    const mapDict = (m && m.mapping) || {}
    Object.keys(mapping).forEach(k => delete mapping[k])
    Object.keys(l || {}).forEach(k => { mapping[k] = mapDict[k] || '' })
    projectOptions.value = (m && m.options) || []
    Object.keys(projectEnabled).forEach(k => delete projectEnabled[k])
    Object.keys(l || {}).forEach(k => { projectEnabled[k] = !(cfg.projects[k] && cfg.projects[k].enabled === false) })
    Object.assign(status, s || {})
    schedulerActive.value = !!s.scheduler_active
  } catch (e) {
    if (e.response?.status === 401) { loading.value = false; return }
  }
  loading.value = false
}

async function loadLogs() {
  try { logs.value = await api.getWorkOrderLogs(80) } catch {}
}

async function saveConfig() {
  try {
    const payload = { enabled: cfg.enabled, weekly_day: cfg.weekly_day, weekly_time: cfg.weekly_time }
    if (phoneInput.value.trim()) payload.creater_phone = phoneInput.value.trim()
    // 同步每项目 enabled
    const projects = {}
    Object.keys(links.value).forEach(k => { projects[k] = { enabled: projectEnabled[k] !== false } })
    payload.projects = projects
    const r = await api.updateWorkOrderConfig(payload)
    ElMessage.success('配置已保存')
    phoneMasked.value = r.creater_phone_masked || phoneMasked.value
    phoneInput.value = ''
    await loadAll()
  } catch (e) { ElMessage.error('保存失败：' + (e.response?.data?.error || e.message)) }
}

async function saveMapping() {
  try {
    await api.updateWorkOrderMapping({ ...mapping })
    ElMessage.success('映射已保存')
    await loadAll()
  } catch (e) { ElMessage.error('保存失败：' + (e.response?.data?.error || e.message)) }
}

async function refreshLinks() {
  refreshing.value = true
  try { await api.refreshWorkOrderLinks(); ElMessage.success('链接已刷新'); await loadAll() }
  catch (e) { ElMessage.error('刷新失败') }
  refreshing.value = false
}

async function startScheduler() {
  try { await api.startWorkOrderScheduler(); ElMessage.success('调度已启动'); await loadAll() }
  catch { ElMessage.error('启动失败') }
}
async function stopScheduler() {
  try { await api.stopWorkOrderScheduler(); ElMessage.success('调度已停止'); await loadAll() }
  catch { ElMessage.error('停止失败') }
}

async function triggerAll() {
  try {
    await ElMessageBox.confirm('将对所有「已配映射且有故障」的项目真实创建工单到 PMS（不可逆）。确认继续？', '立即推送全部', { type: 'warning' })
  } catch { return }
  triggering.value = true
  try {
    const r = await api.triggerWorkOrder()
    const ok = (r.results || []).filter(x => x.success).length
    const skip = (r.results || []).filter(x => x.skipped).length
    const fail = (r.results || []).filter(x => x.error).length
    ElMessage.success(`完成：成功${ok} / 跳过${skip} / 失败${fail}`)
    await loadLogs()
  } catch (e) { ElMessage.error('推送失败：' + (e.response?.data?.error || e.message)) }
  triggering.value = false
}

async function testOne(prj) {
  try {
    await ElMessageBox.confirm(`将对「${prj}」真实创建一条工单到 PMS（不可逆），用于验证链路。继续？`, '测试单项目', { type: 'warning' })
  } catch { return }
  try {
    const r = await api.testWorkOrder(prj)
    if (r.success) ElMessage.success(r.message || `已创建 q_id=${r.q_id}`)
    else if (r.skipped) ElMessage.warning(r.message || '该项目无故障，未发空工单')
    else ElMessage.error(r.error || '测试失败')
    await loadLogs()
  } catch (e) { ElMessage.error('测试失败：' + (e.response?.data?.error || e.message)) }
}

async function preview(prj) {
  const db = mapping[prj]
  if (!db) { ElMessage.warning('请先填写该项目的系统项目名映射'); return }
  try {
    const r = await api.previewWorkOrder(db)
    if (r.skipped) { ElMessage.info(r.message || '该项目无故障数据'); return }
    previewPrj.value = prj
    previewData.value = r
  } catch (e) { ElMessage.error('预览失败：' + (e.response?.data?.error || e.message)) }
}

onMounted(() => {
  loadAll(); loadLogs()
  timer = setInterval(() => { loadAll(); loadLogs() }, 10000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.cfg-card { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow-sm); }
.cfg-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; flex-wrap: wrap; }
.cfg-label { font-size: 12px; color: var(--text-2); width: 96px; flex-shrink: 0; }
.cfg-check { width: 16px; height: 16px; }
.cfg-select, .cfg-time, .cfg-input { font-size: 12px; padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-1); }
.cfg-input { width: 220px; }
.cfg-hint { font-size: 11px; color: var(--text-3); }
.cfg-actions { margin-top: 8px; display: flex; align-items: center; gap: 10px; }
.scheduler-bar { display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 12px 16px; }
.scheduler-status { display: flex; align-items: center; }
.scheduler-actions { display: flex; gap: 8px; }
.sync-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.sync-badge.running { background: rgba(26,127,55,.1); color: var(--green); }
.sync-badge.idle { background: var(--bg-hover); color: var(--text-3); }
.warn-banner { margin-top: 8px; font-size: 11px; color: #b54708; background: rgba(245,158,11,.08); border: 1px solid rgba(245,158,11,.3); border-radius: var(--radius-sm); padding: 8px 12px; }
.map-table { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); overflow: hidden; }
.map-row { display: grid; grid-template-columns: 1.3fr 0.8fr 2fr 0.5fr 1.4fr; gap: 8px; padding: 8px 12px; align-items: center; font-size: 12px; border-bottom: 1px solid var(--border-subtle); }
.map-row:last-child { border-bottom: none; }
.map-head { font-weight: 600; color: var(--text-2); background: var(--bg-hover); }
.map-row.unmapped { background: rgba(248,81,73,.04); }
.map-prj { color: var(--text-1); }
.map-cid { color: var(--text-3); }
.map-input { font-size: 12px; padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-1); width: 100%; }
.map-row.unmapped .map-input { border-color: rgba(248,81,73,.5); }
.map-actions { display: flex; gap: 6px; }
.map-actions button { font-size: 11px; padding: 3px 8px; }
.log-panel { background: #0d1117; border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; max-height: 420px; overflow-y: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; }
.log-line { padding: 2px 0; display: flex; gap: 8px; }
.log-time { color: #6e7681; flex-shrink: 0; }
.log-module { color: #58a6ff; flex-shrink: 0; }
.log-msg { color: #c9d1d9; }
.log-line.error .log-msg { color: #f85149; }
.log-line.success .log-msg { color: #3fb950; }
.log-empty { color: #6e7681; text-align: center; padding: 20px; }
.preview-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.preview-dialog { background: var(--bg-card); border-radius: var(--radius); width: 720px; max-width: 92vw; max-height: 80vh; display: flex; flex-direction: column; box-shadow: var(--shadow-sm); }
.preview-head { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); font-size: 13px; font-weight: 600; }
.preview-meta { padding: 8px 16px; font-size: 11px; color: var(--text-2); border-bottom: 1px solid var(--border-subtle); }
.preview-content { margin: 0; padding: 12px 16px; font-family: 'Consolas', monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; color: var(--text-1); overflow-y: auto; }
</style>
