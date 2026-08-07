<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <Icon name="server" :size="28" />
        <h2>数据管理中心</h2>
      </div>
      <div class="login-subtitle">用户登录</div>
      <form @submit.prevent="handleLogin" class="login-form">
        <select v-model="selectedProject" class="login-select" :disabled="loading">
          <option value="admin">管理员 (全部项目)</option>
          <option v-for="p in projects" :key="p" :value="p">{{ p }}</option>
        </select>
        <input
          v-model="password" type="password" :placeholder="selectedProject === 'admin' ? '管理员密码' : '项目密码'"
          class="login-input" :disabled="loading" autofocus
        />
        <button type="submit" class="login-btn" :disabled="loading || !password">
          {{ loading ? '验证中...' : '登录' }}
        </button>
      </form>
      <div v-if="isDefault && selectedProject === 'admin'" class="login-hint">
        管理员当前使用默认初始密码，请尽快登录后修改
      </div>
      <div v-if="error" class="login-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import api from '../api'

const route = useRoute()
const router = useRouter()
const projects = ref([])
const selectedProject = ref('admin')
const password = ref('')
const loading = ref(false)
const error = ref('')
const isDefault = ref(false)

onMounted(async () => {
  try {
    const [check, data] = await Promise.all([api.authCheck(), api.getAuthProjects()])
    isDefault.value = check.is_default
    projects.value = data.projects || []
  } catch {}
})

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    const result = await api.login(password.value, selectedProject.value)
    localStorage.setItem('admin_token', result.token)
    localStorage.setItem('user_project', result.project)
    localStorage.setItem('is_admin', result.is_admin ? '1' : '0')
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch (e) {
    error.value = e.response?.data?.error || '登录失败'
  }
  loading.value = false
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; height: 100vh; background: var(--bg-page); }
.login-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px; padding: 40px; width: 360px; box-shadow: 0 4px 20px rgba(0,0,0,.08); text-align: center; }
.login-header { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 8px; color: var(--text-1); }
.login-header h2 { margin: 0; font-size: 20px; }
.login-subtitle { color: var(--text-3); font-size: 13px; margin-bottom: 24px; }
.login-form { display: flex; flex-direction: column; gap: 12px; }
.login-select { padding: 10px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 14px; background: var(--bg-page); color: var(--text-1); outline: none; cursor: pointer; }
.login-select:focus { border-color: var(--accent); }
.login-input { padding: 10px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 14px; background: var(--bg-page); color: var(--text-1); outline: none; transition: border-color 0.15s; }
.login-input:focus { border-color: var(--accent); }
.login-btn { padding: 10px; border: none; border-radius: var(--radius-sm); background: var(--accent); color: #fff; font-size: 14px; font-weight: 500; cursor: pointer; transition: opacity 0.15s; }
.login-btn:hover { opacity: 0.9; }
.login-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.login-hint { margin-top: 16px; font-size: 12px; color: var(--text-3); background: var(--bg-hover); padding: 8px; border-radius: var(--radius-sm); }
.login-error { margin-top: 12px; font-size: 12px; color: var(--red); }
</style>
