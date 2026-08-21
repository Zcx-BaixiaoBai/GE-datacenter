<template>
  <div class="page-container" v-loading="loading">
    <!-- 全局设置 -->
    <div class="section-title">通知设置</div>
    <div class="settings-card">
      <div class="notify-global">
        <label class="toggle-row">
          <span>启用每日推送</span>
          <input type="checkbox" v-model="globalCfg.enabled" @change="saveGlobal" />
        </label>
        <div class="time-row">
          <span>推送时间</span>
          <input type="time" v-model="globalCfg.daily_time" @change="saveGlobal" class="time-input" />
        </div>
        <div class="scheduler-section">
          <span>调度:</span>
          <span class="status-tag" :class="schedulerActive ? 'good' : 'bad'">{{ schedulerActive ? '运行中' : '已停止' }}</span>
          <button v-if="!schedulerActive" class="btn-ghost" @click="startScheduler" style="font-size:11px;padding:3px 10px">启动</button>
          <button v-else class="btn-ghost" @click="stopScheduler" style="font-size:11px;padding:3px 10px">停止</button>
          <button class="btn-ghost" @click="triggerAll" style="font-size:11px;padding:3px 10px;margin-left:8px">立即推送全部</button>
        </div>
      </div>
    </div>

    <!-- 扫码绑定 -->
    <div class="section-title" style="margin-top:20px">扫码绑定</div>
    <div class="qr-tabs">
      <button class="btn-ghost" :class="{active: qrTab==='wechat'}" @click="switchTab('wechat')" style="font-size:12px">微信</button>
      <button class="btn-ghost" :class="{active: qrTab==='feishu'}" @click="switchTab('feishu')" style="font-size:12px">飞书</button>
      <button class="btn-ghost" @click="loadQrcode" style="font-size:12px">刷新二维码</button>
    </div>
    <div class="qr-area">
      <div v-if="qrLoading" class="qr-loading">生成中...</div>
      <img v-else-if="qrImg" :src="qrImg" class="qr-img" @click="loadQrcode" title="点击刷新" />
      <div v-else class="qr-placeholder">点击"刷新二维码"获取{{ qrTab === 'wechat' ? '微信' : '飞书' }}扫码二维码</div>
      <div v-if="qrStatus" class="qr-status" :class="qrStatusClass">{{ qrStatusText }}</div>
    </div>

    <!-- 微信提示 -->
    <div class="alert-box alert-warn" v-if="qrTab === 'wechat' && qrStatus === 'confirmed'">
      <div class="alert-title">微信扫码成功！请立即完成下一步</div>
      <div class="alert-content">
        微信 bot 无法主动发起对话。<b>请在微信中找到该 bot，发一条消息（任意内容即可）</b>。
        只有用户先发消息，bot 才能向该用户推送通知日报。
      </div>
    </div>
    <div class="alert-box" v-if="qrTab === 'wechat' && wechatStatus && wechatStatus.logged_in && qrStatus !== 'confirmed'">
      <div class="alert-title">微信推送说明</div>
      <div class="alert-content">
        微信 bot 无法主动发起对话。用户扫码登录后，<b>必须先发一条消息给 bot</b>，系统才能获取推送所需的 context_token。
        <br/>未激活的用户需要先发消息，否则推送会报"用户未激活"。
      </div>
    </div>

    <!-- 飞书绑定状态 -->
    <div class="alert-box" v-if="qrTab === 'feishu' && feishuStatus && feishuStatus.bound" style="background:rgba(26,127,55,.06);border-color:rgba(26,127,55,.2)">
      <div class="alert-title" style="color:var(--green)">飞书已绑定</div>
      <div class="alert-content">
        绑定时间: {{ feishuStatus.bind_time }}<br/>
        飞书可以主动推送消息，无需用户先发消息。点击"测试"验证推送是否正常。
      </div>
    </div>

    <!-- 已绑定用户 (微信+飞书统一) -->
    <div class="section-title" style="margin-top:20px">已绑定用户 <span v-if="!isAdm" style="font-size:11px;color:var(--text-3);margin-left:8px">(您的项目: {{ userProj }})</span></div>
    <table class="data-table">
      <thead><tr><th>渠道</th><th>用户</th><th>名称</th><th>状态</th><th>分配项目</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="u in displayUsers" :key="u.user_id">
          <td>{{ u.channel === 'wechat' ? '微信' : u.channel === 'feishu' ? '飞书' : '邮件' }}</td>
          <td style="font-size:11px">{{ u.user_id.substring(0,25) }}...</td>
          <td>{{ u.name }}</td>
          <td><span class="status-tag" :class="u.active ? 'good' : 'bad'">{{ u.active ? '已激活' : '未激活(需发消息)' }}</span></td>
          <td>
            <span v-if="!isAdm" style="font-size:12px;font-weight:600">{{ userProj }}</span>
            <select v-else v-model="userProjectAssign[u.user_id]" @change="assignProject(u)" class="form-select" style="font-size:11px;padding:3px 6px">
              <option value="">未分配</option>
              <option v-for="p in projectList" :key="p" :value="p">{{ p }}</option>
            </select>
          </td>
          <td>
            <button v-if="u.active && (isAdm ? userProjectAssign[u.user_id] : true)" class="btn-ghost" @click="testSend(isAdm ? userProjectAssign[u.user_id] : userProj)" style="font-size:11px;padding:2px 8px">测试</button>
            <button v-if="isAdm" class="btn-ghost" @click="removeUser(u.user_id)" style="font-size:11px;padding:2px 8px;margin-left:4px">删除</button>
          </td>
        </tr>
        <tr v-if="!displayUsers.length"><td colspan="6" style="text-align:center;color:var(--text-3)">暂无已绑定用户，请扫码绑定</td></tr>
      </tbody>
    </table>

    <!-- 已配置推送项目 -->
    <div class="section-title" style="margin-top:20px">已配置推送项目</div>
    <table class="data-table">
      <thead><tr><th>项目</th><th>渠道</th><th>目标用户</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="(cfg, name) in projects" :key="name">
          <td>{{ name }}</td>
          <td>{{ cfg.channel === 'wechat' ? '微信' : cfg.channel === 'feishu' ? '飞书' : '邮件' }}</td>
          <td style="font-size:11px">{{ cfg.target_user?.substring(0,20) }}...</td>
          <td><span class="status-tag" :class="cfg.enabled ? 'good' : 'bad'">{{ cfg.enabled ? '启用' : '禁用' }}</span></td>
          <td>
            <button class="btn-ghost" @click="testSend(name)" style="font-size:11px;padding:2px 8px">测试</button>
            <button class="btn-ghost" @click="removeProject(name)" style="font-size:11px;padding:2px 8px;margin-left:4px">删除</button>
          </td>
        </tr>
        <tr v-if="!Object.keys(projects).length"><td colspan="5" style="text-align:center;color:var(--text-3)">暂无配置</td></tr>
      </tbody>
    </table>

    <!-- 新增邮件渠道配置 (管理员) -->
    <div v-if="isAdm" style="margin-top:12px;padding:10px;border:1px dashed var(--border);border-radius:6px">
      <div style="font-size:12px;font-weight:600;margin-bottom:8px">新增邮件推送配置</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select v-model="newEmailCfg.project_name" class="form-select" style="font-size:11px;padding:3px 6px;width:140px">
          <option value="">选择项目</option>
          <option v-for="p in projectList" :key="p" :value="p">{{ p }}</option>
        </select>
        <input v-model="newEmailCfg.target_user" placeholder="收件邮箱地址" class="form-input" style="font-size:11px;padding:3px 8px;width:220px" />
        <button class="btn-primary" @click="addEmailNotify" style="font-size:11px;padding:3px 12px">添加</button>
      </div>
    </div>

    <!-- 日志 -->
    <div class="section-title" style="margin-top:20px">推送日志</div>
    <div class="log-panel">
      <div class="log-line" v-for="(log, i) in logs" :key="i" :class="log.status">
        <span class="log-time">{{ log.date }} {{ log.time }}</span>
        <span class="log-module">[{{ log.project }}]</span>
        <span class="log-msg">{{ log.msg }}</span>
      </div>
      <div v-if="!logs.length" class="log-empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const loading = ref(true)
const globalCfg = reactive({ enabled: false, daily_time: '09:00' })
const schedulerActive = ref(false)
const projects = ref({})
const projectList = ref([])
const logs = ref([])
const wechatStatus = ref(null)
const feishuStatus = ref(null)
const feishuResult = ref(null)

const isAdm = localStorage.getItem('is_admin') === '1'
const userProj = localStorage.getItem('user_project') || ''
const userProjectAssign = reactive({})

const qrTab = ref('wechat')
const qrImg = ref('')
const qrToken = ref('')
const qrLoading = ref(false)
const qrStatus = ref('')
let timer = null
const qrPollTimers = []

async function loadAll() {
  try {
    const promises = [api.getNotifyConfig(), api.getNotifyStatus(), api.getProjects(), api.getNotifyLogs(50), api.getWechatStatus()]
    if (isAdm) promises.push(api.getFeishuStatus())
    const results = await Promise.all(promises)
    const [cfg, status, projData, logData, wxStatus, fsStatus] = results
    globalCfg.enabled = cfg.enabled
    globalCfg.daily_time = cfg.daily_time
    projects.value = cfg.projects || {}
    schedulerActive.value = status.scheduler_active
    projectList.value = [...new Set((projData || []).map(p => p.project_name).filter(Boolean))]
    logs.value = logData
    wechatStatus.value = wxStatus
    if (fsStatus) feishuStatus.value = fsStatus
    for (const [name, pcfg] of Object.entries(projects.value)) {
      if (pcfg.target_user) userProjectAssign[pcfg.target_user] = name
    }
    // 项目用户: 自动绑定新用户到自己的项目
    if (!isAdm && userProj) {
      for (const u of (wxStatus?.users || [])) {
        if (!projects.value[userProj] && u.active) {
          await api.setNotifyProject({ project_name: userProj, channel: u.channel, target_user: u.user_id, target_session: u.user_id, enabled: true })
          projects.value[userProj] = { channel: u.channel, target_user: u.user_id, enabled: true }
        }
      }
    }
  } catch (e) {
    if (e.response?.status === 401) { ElMessage.error('请先登录'); loading.value = false; return }
  }
  loading.value = false
}

function switchTab(tab) {
  qrTab.value = tab
  qrImg.value = ''
  qrStatus.value = ''
  qrPollTimers.forEach(clearInterval)
}

async function loadQrcode() {
  qrLoading.value = true
  qrImg.value = ''
  qrStatus.value = ''
  try {
    const data = await api.getQrcode(qrTab.value)
    if (data.qrcode_img) {
      qrImg.value = `data:image/png;base64,${data.qrcode_img}`
      qrToken.value = data.poll_token
      qrStatus.value = 'waiting'
      startPolling()
    } else if (data.error) {
      qrStatus.value = 'error'
    }
  } catch { qrStatus.value = 'error' }
  qrLoading.value = false
}

function startPolling() {
  qrPollTimers.forEach(clearInterval)
  qrPollTimers.length = 0
  const t = setInterval(async () => {
    try {
      const data = await api.getQrcodeStatus(qrTab.value, qrToken.value)
      if (data.status === 'confirmed' || data.confirmed) {
        qrStatus.value = 'confirmed'
        clearInterval(t)
        ElMessage.success(`${qrTab.value === 'wechat' ? '微信' : '飞书'}扫码绑定成功!`)
        await loadAll()
      } else if (data.status === 'expired' || data.status === 'timeout') {
        qrStatus.value = 'expired'
        clearInterval(t)
      } else if (data.status === 'denied') {
        qrStatus.value = 'denied'
        clearInterval(t)
      } else if (data.status === 'scanned') {
        qrStatus.value = 'scanned'
      }
    } catch {}
  }, 3000)
  qrPollTimers.push(t)
  setTimeout(() => clearInterval(t), 180000)
}

const qrStatusText = computed(() => ({
  waiting: '等待扫码...', scanned: '已扫码, 等待确认...',
  confirmed: qrTab.value === 'wechat' ? '登录成功! 请在微信中发一条消息给bot' : '飞书绑定成功!',
  expired: '二维码已过期, 请刷新', error: '获取失败, 请重试',
  denied: '授权被拒绝'
}[qrStatus.value] || ''))
const qrStatusClass = computed(() => (qrStatus.value === 'confirmed' ? 'good' : (qrStatus.value === 'expired' || qrStatus.value === 'error' || qrStatus.value === 'denied') ? 'bad' : ''))

async function assignProject(user) {
  const project = userProjectAssign[user.user_id]
  if (!project) return
  try {
    await api.setNotifyProject({
      project_name: project,
      channel: user.channel,
      target_user: user.user_id,
      target_session: user.user_id,
      enabled: true,
    })
    ElMessage.success(`已将 ${user.name} 分配给 ${project}`)
    loadAll()
  } catch { ElMessage.error('分配失败') }
}

const allUsers = computed(() => {
  if (!wechatStatus.value) return []
  return wechatStatus.value.users || []
})

// 项目用户只看自己项目的绑定
const displayUsers = computed(() => {
  if (isAdm) return allUsers.value
  if (!userProj) return []
  // 只显示分配给自己项目的用户
  return allUsers.value.filter(u => {
    const assign = userProjectAssign[u.user_id]
    return assign === userProj
  })
})

async function saveGlobal() { try { await api.updateNotifyConfig({ ...globalCfg }) } catch {} }
async function startScheduler() { try { await api.startNotifyScheduler(); ElMessage.success('已启动'); loadAll() } catch { ElMessage.error('启动失败') } }
async function stopScheduler() { try { await api.stopNotifyScheduler(); ElMessage.success('已停止'); loadAll() } catch { ElMessage.error('停止失败') } }
async function triggerAll() { try { const r = await api.triggerNotify(); ElMessage.success(`已推送 ${r.total} 个项目`) } catch { ElMessage.error('推送失败') } }
async function testSend(name) { try { const r = await api.testNotify(name); r.success ? ElMessage.success(r.message || '已发送') : ElMessage.error(r.error) } catch (e) { ElMessage.error(e.response?.data?.error || '发送失败') } }
async function removeProject(name) { try { await api.deleteNotifyProject(name); ElMessage.success('已删除'); loadAll() } catch { ElMessage.error('删除失败') } }
async function removeUser(uid) { try { await api.removeNotifyUser(uid); ElMessage.success('已删除用户'); loadAll() } catch { ElMessage.error('删除失败') } }

const newEmailCfg = reactive({ project_name: '', target_user: '' })
async function addEmailNotify() {
  if (!newEmailCfg.project_name) { ElMessage.warning('请选择项目'); return }
  if (!newEmailCfg.target_user || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(newEmailCfg.target_user)) { ElMessage.warning('请输入有效的邮箱地址'); return }
  try {
    await api.setNotifyProject({ project_name: newEmailCfg.project_name, channel: 'email', target_user: newEmailCfg.target_user, target_session: newEmailCfg.target_user, enabled: true })
    ElMessage.success('邮件配置已添加')
    newEmailCfg.project_name = ''
    newEmailCfg.target_user = ''
    loadAll()
  } catch (e) { ElMessage.error(e.response?.data?.error || '添加失败') }
}
async function testFeishu() { try { feishuResult.value = await api.testFeishu() } catch (e) { feishuResult.value = { ok: false, msg: e.response?.data?.error || '测试失败' } } }

onMounted(async () => { await loadAll(); timer = setInterval(loadAll, 10000) })
onUnmounted(() => { if (timer) clearInterval(timer); qrPollTimers.forEach(clearInterval) })
</script>

<style scoped>
.settings-card { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow-sm); }
.notify-global { display: flex; flex-direction: column; gap: 12px; }
.toggle-row { display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; }
.toggle-row input { width: 16px; height: 16px; cursor: pointer; }
.time-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.time-input { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px 8px; font-size: 13px; background: var(--bg-page); color: var(--text-1); }
.scheduler-section { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.form-actions { display: flex; gap: 8px; align-items: center; }
.form-select { border: 1px solid var(--border-subtle); border-radius: 4px; background: var(--bg-page); color: var(--text-1); outline: none; }
.qr-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.qr-area { display: flex; flex-direction: column; align-items: center; padding: 20px; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); margin-bottom: 16px; }
.qr-img { width: 220px; height: 220px; border-radius: var(--radius-sm); cursor: pointer; }
.qr-loading, .qr-placeholder { color: var(--text-3); font-size: 13px; padding: 80px 20px; text-align: center; }
.qr-status { margin-top: 12px; font-size: 13px; font-weight: 500; }
.qr-status.good { color: var(--green); }
.qr-status.bad { color: var(--red); }
.alert-box { background: rgba(9,105,218,.06); border: 1px solid rgba(9,105,218,.2); border-radius: var(--radius); padding: 14px 16px; margin-bottom: 16px; }
.alert-box.alert-warn { background: rgba(207,34,46,.06); border-color: rgba(207,34,46,.2); }
.alert-title { font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: 6px; }
.alert-warn .alert-title { color: var(--red); }
.alert-content { font-size: 12px; color: var(--text-2); line-height: 1.6; }
.log-panel { background: #0d1117; border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; max-height: 300px; overflow-y: auto; font-family: 'Consolas', monospace; font-size: 12px; }
.log-line { padding: 2px 0; display: flex; gap: 8px; }
.log-time { color: #6e7681; flex-shrink: 0; }
.log-module { color: #58a6ff; flex-shrink: 0; }
.log-msg { color: #c9d1d9; }
.log-line.error .log-msg { color: #f85149; }
.log-line.success .log-msg { color: #3fb950; }
.log-empty { color: #6e7681; text-align: center; padding: 20px; }
</style>
