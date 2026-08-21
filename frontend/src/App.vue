<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <Icon name="server" :size="18" />
        <span class="brand">数据管理中心</span>
      </div>
      <nav class="nav-list">
        <router-link v-for="item in visibleMenu" :key="item.path" :to="item.path" class="nav-item" active-class="active">
          <Icon :name="item.icon" :size="16" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <template v-if="authed">
          <div class="user-info">
            <span class="user-project">{{ userProjectLabel }}</span>
          </div>
          <button class="btn-ghost logout-btn" @click="handleLogout">退出登录</button>
        </template>
        <template v-else>
          <router-link to="/login" class="btn-ghost login-btn">
            <Icon name="shield" :size="14" />
            <span>登录</span>
          </router-link>
        </template>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <span class="topbar-title">{{ title }}</span>
        <div class="topbar-actions" v-if="isAdmin">
          <label class="btn-ghost" :class="{ loading: uploading }">
            <Icon name="refresh" :size="14" />
            <span>{{ uploading ? '同步中...' : '数据同步' }}</span>
            <input type="file" accept=".xlsx,.xlsm" style="display:none" @change="handleUpload" />
          </label>
        </div>
      </header>
      <div class="content">
        <router-view />
      </div>
    </main>

    <AIWidget />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import Icon from './components/Icon.vue'
import AIWidget from './components/AIWidget.vue'
import api from './api'

const route = useRoute()
const router = useRouter()
const syncInfo = ref(null)
const uploading = ref(false)
const authed = ref(false)
const isAdmin = ref(false)
const userProject = ref('')
const menu = [
  { path: '/', label: '集团总览', icon: 'dashboard', public: true },
  { path: '/meters', label: '瑞信电表', icon: 'zap', public: true },
  { path: '/safety', label: '金鹰安全', icon: 'shield', public: true },
  { path: '/equipment', label: '设备管理', icon: 'cpu', public: true },
  { path: '/budget', label: '预算使用', icon: 'budget', public: true },
  { path: '/notify', label: '通知推送', icon: 'alert', public: false },
  { path: '/workorder', label: '工单推送', icon: 'activity', adminOnly: true },
  { path: '/sync-center', label: '数据同步', icon: 'server', adminOnly: true },
  { path: '/admin', label: '管理设置', icon: 'cpu', adminOnly: true },
]

const visibleMenu = computed(() => menu.filter(m => {
  if (m.public) return true
  if (m.adminOnly) return isAdmin.value
  return authed.value  // 通知推送: 登录用户都可访问
}))

const title = computed(() => route.meta.title || '数据管理中心')
const userProjectLabel = computed(() => {
  if (isAdmin.value) return '管理员'
  return userProject.value || '已登录'
})

function refreshAuth() {
  const token = localStorage.getItem('admin_token')
  if (!token) {
    authed.value = false; isAdmin.value = false; userProject.value = ''
    return
  }
  // 先同步设置为false, 异步验证后再恢复
  api.authCheck().then(r => {
    if (!r.authenticated) {
      localStorage.removeItem('admin_token')
      localStorage.removeItem('user_project')
      localStorage.removeItem('is_admin')
      authed.value = false; isAdmin.value = false; userProject.value = ''
    } else {
      authed.value = true
      isAdmin.value = r.is_admin
      userProject.value = r.project || ''
      localStorage.setItem('is_admin', r.is_admin ? '1' : '0')
      localStorage.setItem('user_project', r.project || '')
    }
  }).catch(() => {
    authed.value = false; isAdmin.value = false; userProject.value = ''
  })
}

// 页面加载时立即执行(同步清旧token)
watch(() => route.path, () => {
  const token = localStorage.getItem('admin_token')
  // 检查token格式是否是新的3段式(ts.sig.encoded_project)
  if (token && token.split('.').length !== 3) {
    localStorage.removeItem('admin_token')
    localStorage.removeItem('user_project')
    localStorage.removeItem('is_admin')
    authed.value = false; isAdmin.value = false; userProject.value = ''
    return
  }
  refreshAuth()
}, { immediate: true })

async function loadSync() {
  try { syncInfo.value = await api.getSyncStatus() } catch {}
}

async function handleUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const result = await api.syncFile(file)
    if (result.success) ElMessage.success(`同步完成: ${result.total_rows} 行`)
    else ElMessage.warning(`同步有错误: ${result.errors?.join(', ')}`)
    await loadSync(); window.location.reload()
  } catch (e) { ElMessage.error('同步失败: ' + (e.response?.data?.error || e.message)) }
  uploading.value = false; e.target.value = ''
}

async function handleLogout() {
  try { await api.logout() } catch {}
  localStorage.removeItem('admin_token')
  localStorage.removeItem('user_project')
  localStorage.removeItem('is_admin')
  authed.value = false; isAdmin.value = false; userProject.value = ''
  ElMessage.success('已退出登录')
  router.push('/')
}

onMounted(loadSync)
</script>

<style scoped>
.app-layout { display: flex; height: 100vh; overflow: hidden; }
.sidebar { width: 192px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-header { padding: 16px 14px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border-subtle); color: var(--text-1); }
.sidebar-header .brand { font-size: 13px; font-weight: 600; }
.nav-list { flex: 1; padding: 6px 8px; overflow-y: auto; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 7px 12px; color: var(--text-2); text-decoration: none; font-size: 12px; border-radius: var(--radius-sm); transition: all 0.12s; }
.nav-item:hover { color: var(--text-1); background: var(--bg-hover); }
.nav-item.active { color: var(--accent); background: rgba(9,105,218,.08); }
.sidebar-footer { padding: 10px 14px; border-top: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: 8px; }
.user-info { font-size: 11px; color: var(--text-2); }
.user-project { font-weight: 600; }
.login-btn, .logout-btn { width: 100%; justify-content: center; font-size: 11px; padding: 5px 10px; text-decoration: none; }
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.topbar { height: 44px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; flex-shrink: 0; }
.topbar-title { font-size: 14px; font-weight: 600; color: var(--text-1); }
.content { flex: 1; overflow-y: auto; }
.btn-ghost.loading { opacity: .6; pointer-events: none; }
</style>
