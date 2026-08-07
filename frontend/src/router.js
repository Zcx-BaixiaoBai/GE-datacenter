import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '集团总览' } },
  { path: '/meters', name: 'meters', component: () => import('./views/Meters.vue'), meta: { title: '瑞信电表' } },
  { path: '/safety', name: 'safety', component: () => import('./views/Safety.vue'), meta: { title: '金鹰安全' } },
  { path: '/equipment', name: 'equipment', component: () => import('./views/Equipment.vue'), meta: { title: '设备管理' } },
  { path: '/budget', name: 'budget', component: () => import('./views/Budget.vue'), meta: { title: '预算使用' } },
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { title: '登录' } },
  { path: '/notify', name: 'notify', component: () => import('./views/NotifySettings.vue'), meta: { title: '通知推送', requiresAuth: true } },
  { path: '/sync-center', name: 'syncCenter', component: () => import('./views/SyncCenter.vue'), meta: { title: '数据同步', requiresAdmin: true } },
  { path: '/admin', name: 'admin', component: () => import('./views/AdminSettings.vue'), meta: { title: '管理设置', requiresAdmin: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth || to.meta.requiresAdmin) {
    const token = localStorage.getItem('admin_token')
    if (!token) {
      next({ name: 'login', query: { redirect: to.fullPath } })
      return
    }
  }
  if (to.meta.requiresAdmin) {
    const isAdmin = localStorage.getItem('is_admin') === '1'
    if (!isAdmin) {
      next({ name: 'overview' })
      return
    }
  }
  next()
})

export default router
