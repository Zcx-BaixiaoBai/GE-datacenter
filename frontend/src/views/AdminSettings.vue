<template>
  <div class="page-container" v-loading="loading">
    <!-- AI 配置 -->
    <div class="section-title">AI 沟通配置</div>
    <div class="settings-card">
      <div class="form-row">
        <label>API 地址</label>
        <input v-model="cfg.api_url" class="form-input" placeholder="https://api.openai.com/v1/chat/completions" />
      </div>
      <div class="form-row">
        <label>API Key</label>
        <input v-model="cfg.api_key" type="password" class="form-input" :placeholder="cfg.api_key_masked || '输入 API Key'" />
      </div>
      <div class="form-row">
        <label>模型名称</label>
        <input v-model="cfg.model" class="form-input" placeholder="gpt-4o" />
      </div>
      <div class="form-row">
        <label>系统提示词</label>
        <textarea v-model="cfg.system_prompt" class="form-textarea" rows="4" placeholder="AI的角色定义和行为指令"></textarea>
      </div>
      <div class="form-row-inline">
        <div class="form-row" style="flex:1">
          <label>温度 (0-1)</label>
          <input v-model.number="cfg.temperature" type="number" min="0" max="1" step="0.1" class="form-input" />
        </div>
        <div class="form-row" style="flex:1; margin-left:16px">
          <label>最大 Token</label>
          <input v-model.number="cfg.max_tokens" type="number" class="form-input" />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn-ghost" @click="testAI" :disabled="testing">{{ testing ? '测试中...' : '测试连接' }}</button>
        <button class="btn-ghost active" @click="saveAI" :disabled="saving">{{ saving ? '保存中...' : '保存配置' }}</button>
      </div>
      <div v-if="testResult" class="form-feedback" :class="testResult.ok ? 'ok' : 'err'">
        {{ testResult.msg }}
      </div>
    </div>

    <!-- 数据上下文预览 -->
    <div class="section-title" style="margin-top:24px">AI 数据上下文 (预览)</div>
    <div class="settings-card">
      <p style="font-size:12px;color:var(--text-3);margin:0 0 12px">AI对话时自动注入以下数据作为上下文:</p>
      <pre class="context-preview">{{ contextPreview }}</pre>
    </div>

    <!-- 项目用户密码管理 -->
    <div class="section-title" style="margin-top:24px">项目用户密码管理</div>
    <div class="settings-card">
      <p style="font-size:12px;color:var(--text-3);margin:0 0 12px">为每个项目设置登录密码，项目用户在登录页选择项目后用此密码登录，只能看到自己项目的通知推送。</p>
      <div class="project-pwd-list">
        <div v-for="p in allProjects" :key="p" class="project-pwd-row">
          <span class="project-name">{{ p }}</span>
          <input v-model="projectPasswords[p]" :type="showPwd[p] ? 'text' : 'password'" class="form-input project-pwd-input" :placeholder="configuredProjects.includes(p) ? '已设置(输入新密码修改)' : '未设置'" />
          <button class="btn-ghost" @click="showPwd[p] = !showPwd[p]" style="font-size:11px;padding:3px 8px">{{ showPwd[p] ? '隐藏' : '显示' }}</button>
          <button class="btn-ghost active" @click="setProjectPwd(p)" style="font-size:11px;padding:3px 10px" :disabled="!projectPasswords[p]">设置</button>
        </div>
      </div>
    </div>

    <!-- 密码修改 -->
    <div class="section-title" style="margin-top:24px">管理员密码</div>
    <div class="settings-card">
      <div class="form-row">
        <label>旧密码</label>
        <input v-model="pwdForm.old" type="password" class="form-input" />
      </div>
      <div class="form-row">
        <label>新密码</label>
        <input v-model="pwdForm.new" type="password" class="form-input" />
      </div>
      <div class="form-row">
        <label>确认新密码</label>
        <input v-model="pwdForm.confirm" type="password" class="form-input" />
      </div>
      <div class="form-actions">
        <button class="btn-ghost" @click="changePwd" :disabled="!pwdForm.old || !pwdForm.new">修改密码</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const cfg = ref({})
const testResult = ref(null)
const contextPreview = ref('')
const pwdForm = ref({ old: '', new: '', confirm: '' })
const allProjects = ref([])
const configuredProjects = ref([])
const projectPasswords = reactive({})
const showPwd = reactive({})

import { reactive } from 'vue'

onMounted(async () => {
  try {
    cfg.value = await api.getAIConfig()
    try { contextPreview.value = await api.get('/ai/data-context') } catch(e) { console.error('context load failed', e) }
    // 获取项目列表和已配置密码的项目
    const data = await api.getAuthProjects()
    allProjects.value = data.projects || []
    configuredProjects.value = data.configured || []
  } catch (e) {
    if (e.response?.status === 401) { ElMessage.error('请先登录'); loading.value = false; return }
  }
  loading.value = false
})

async function saveAI() {
  saving.value = true
  try {
    const update = { ...cfg.value }
    // 如果key为空则不更新
    if (!update.api_key) delete update.api_key
    cfg.value = await api.updateAIConfig(update)
    ElMessage.success('AI配置已保存')
  } catch (e) { ElMessage.error('保存失败') }
  saving.value = false
}

async function testAI() {
  testing.value = true
  testResult.value = null
  try {
    // 先保存再测试
    await saveAI()
    testResult.value = await api.testAI()
  } catch (e) { testResult.value = { ok: false, msg: '测试失败' } }
  testing.value = false
}

async function changePwd() {
  if (pwdForm.value.new !== pwdForm.value.confirm) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  if (pwdForm.value.new.length < 6) {
    ElMessage.error('新密码至少6位')
    return
  }
  try {
    const r = await api.changePassword(pwdForm.value.old, pwdForm.value.new)
    if (r.success) {
      ElMessage.success('密码修改成功, 请重新登录')
      localStorage.removeItem('admin_token')
      setTimeout(() => window.location.href = '/login', 1500)
    } else {
      ElMessage.error(r.message)
    }
  } catch (e) { ElMessage.error('修改失败') }
}

async function setProjectPwd(project) {
  const pwd = projectPasswords[project]
  if (!pwd || pwd.length < 4) {
    ElMessage.error('密码至少4位')
    return
  }
  try {
    await api.setProjectPassword(project, pwd)
    ElMessage.success(`${project} 密码已设置`)
    if (!configuredProjects.value.includes(project)) {
      configuredProjects.value.push(project)
    }
    projectPasswords[project] = ''
  } catch (e) { ElMessage.error('设置失败') }
}
</script>

<style scoped>
.settings-card { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow-sm); }
.form-row { margin-bottom: 14px; }
.form-row label { display: block; font-size: 12px; color: var(--text-3); margin-bottom: 6px; font-weight: 500; }
.form-input {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-page); color: var(--text-1); font-size: 13px; outline: none; transition: border-color 0.15s;
  font-family: inherit;
}
.form-input:focus { border-color: var(--accent); }
.form-textarea { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-page); color: var(--text-1); font-size: 13px; outline: none; font-family: inherit; resize: vertical; }
.form-row-inline { display: flex; }
.form-actions { display: flex; gap: 8px; margin-top: 16px; }
.form-feedback { margin-top: 12px; padding: 8px 12px; border-radius: var(--radius-sm); font-size: 12px; }
.form-feedback.ok { background: rgba(26,127,55,.08); color: var(--green); }
.form-feedback.err { background: rgba(207,34,46,.08); color: var(--red); }
.context-preview {
  background: #0d1117; border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 12px; font-size: 11px; color: #8b949e; max-height: 300px; overflow-y: auto;
  font-family: 'Consolas', monospace; white-space: pre-wrap; margin: 0;
}
.project-pwd-list { max-height: 400px; overflow-y: auto; }
.project-pwd-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border-subtle); }
.project-pwd-row .project-name { min-width: 140px; font-size: 12px; color: var(--text-2); flex-shrink: 0; }
.project-pwd-input { flex: 1; font-size: 12px; padding: 4px 8px; }
</style>
