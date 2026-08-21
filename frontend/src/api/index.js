import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('admin_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default {
  // 原始请求
  get: (url, config) => api.get(url, config).then(r => r.data),
  post: (url, data, config) => api.post(url, data, config).then(r => r.data),

  // 基础数据
  getSummary: () => api.get('/summary').then(r => r.data),
  getMeters: () => api.get('/meters').then(r => r.data),
  getSafety: () => api.get('/safety').then(r => r.data),
  getEquipment: () => api.get('/equipment').then(r => r.data),
  getBudget: () => api.get('/budget').then(r => r.data),
  getProjects: () => api.get('/projects').then(r => r.data),
  getSyncStatus: () => api.get('/sync/status').then(r => r.data),
  syncFile: (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/sync', fd, { timeout: 120000 }).then(r => r.data) },
  getMetersDetail: (p) => api.get('/meters/detail', { params: p }).then(r => r.data),
  getEquipmentDetail: (p) => api.get('/equipment/detail', { params: p }).then(r => r.data),
  getHazards: (p) => api.get('/safety/hazards', { params: p }).then(r => r.data),
  getDuties: (p) => api.get('/safety/duties', { params: p }).then(r => r.data),

  // 认证
  login: (pwd, project) => api.post('/auth/login', { password: pwd, project }).then(r => r.data),
  authCheck: () => api.get('/auth/check').then(r => r.data),
  getAuthProjects: () => api.get('/auth/projects').then(r => r.data),
  logout: () => api.post('/auth/logout').then(r => r.data),
  changePassword: (oldPwd, newPwd) => api.post('/auth/change-password', { old_password: oldPwd, new_password: newPwd }).then(r => r.data),
  setProjectPassword: (project, pwd) => api.post('/notify/project-password', { project, password: pwd }).then(r => r.data),

  // 同步中心
  getSyncCenterStatus: () => api.get('/sync-center/status').then(r => r.data),
  triggerSync: (mid) => api.post('/sync-center/trigger', { module: mid }).then(r => r.data),
  triggerAllSync: () => api.post('/sync-center/trigger-all').then(r => r.data),
  startScheduler: () => api.post('/sync-center/scheduler/start').then(r => r.data),
  stopScheduler: () => api.post('/sync-center/scheduler/stop').then(r => r.data),
  getSyncConfig: () => api.get('/sync-center/config').then(r => r.data),
  updateSyncConfig: (cfg) => api.post('/sync-center/config', cfg).then(r => r.data),
  getSyncLogs: (limit = 50) => api.get('/sync-center/logs', { params: { limit } }).then(r => r.data),

  // AI
  aiChat: (message, history, userId) => api.post('/ai/chat', { message, history, user_id: userId }, { timeout: 120000 }).then(r => r.data),
  getAIConfig: () => api.get('/ai/config').then(r => r.data),
  updateAIConfig: (cfg) => api.post('/ai/config', cfg).then(r => r.data),
  testAI: () => api.post('/ai/test').then(r => r.data),

  // 通知推送 (独立实现, 不依赖 QwenPaw)
  getNotifyConfig: () => api.get('/notify/config').then(r => r.data),
  updateNotifyConfig: (cfg) => api.post('/notify/config', cfg).then(r => r.data),
  setNotifyProject: (data) => api.post('/notify/project', data).then(r => r.data),
  deleteNotifyProject: (project) => api.delete('/notify/project', { params: { project } }).then(r => r.data),
  removeNotifyUser: (uid) => api.delete('/notify/user', { params: { uid } }).then(r => r.data),
  testNotify: (project) => api.post('/notify/test', { project_name: project }).then(r => r.data),
  triggerNotify: () => api.post('/notify/trigger').then(r => r.data),
  getNotifyLogs: (limit = 50) => api.get('/notify/logs', { params: { limit } }).then(r => r.data),
  startNotifyScheduler: () => api.post('/notify/scheduler/start').then(r => r.data),
  stopNotifyScheduler: () => api.post('/notify/scheduler/stop').then(r => r.data),
  getNotifyStatus: () => api.get('/notify/status').then(r => r.data),
  // 微信 (独立 iLink API)
  getQrcode: (channel) => api.get(`/notify/qrcode/${channel}`).then(r => r.data),
  getQrcodeStatus: (channel, token) => api.get(`/notify/qrcode/${channel}/status`, { params: { token } }).then(r => r.data),
  getWechatStatus: () => api.get('/notify/wechat/status').then(r => r.data),
  // 飞书 (WebSocket + Open API)
  getFeishuStatus: () => api.get('/notify/feishu/status').then(r => r.data),
  testFeishu: () => api.post('/notify/feishu/test').then(r => r.data),
  startFeishuWs: () => api.post('/notify/feishu/ws/start').then(r => r.data),
  stopFeishuWs: () => api.post('/notify/feishu/ws/stop').then(r => r.data),
  startWechatPoller: () => api.post('/notify/wechat/poller/start').then(r => r.data),
  stopWechatPoller: () => api.post('/notify/wechat/poller/stop').then(r => r.data),

  // 工单推送 (PMS 工单系统, 每周定时, 独立于日报)
  getWorkOrderConfig: () => api.get('/workorder/config').then(r => r.data),
  updateWorkOrderConfig: (cfg) => api.post('/workorder/config', cfg).then(r => r.data),
  getWorkOrderLinks: () => api.get('/workorder/links').then(r => r.data),
  refreshWorkOrderLinks: () => api.post('/workorder/links/refresh', {}).then(r => r.data),
  getWorkOrderMapping: () => api.get('/workorder/mapping').then(r => r.data),
  updateWorkOrderMapping: (mapping) => api.post('/workorder/mapping', { mapping }).then(r => r.data),
  getWorkOrderTypes: () => api.get('/workorder/types').then(r => r.data),
  getWorkOrderStatus: () => api.get('/workorder/status').then(r => r.data),
  startWorkOrderScheduler: () => api.post('/workorder/scheduler/start').then(r => r.data),
  stopWorkOrderScheduler: () => api.post('/workorder/scheduler/stop').then(r => r.data),
  triggerWorkOrder: () => api.post('/workorder/trigger').then(r => r.data),
  testWorkOrder: (project) => api.post('/workorder/test', { project }).then(r => r.data),
  getWorkOrderLogs: (limit = 50) => api.get('/workorder/logs', { params: { limit } }).then(r => r.data),
  previewWorkOrder: (project) => api.get('/workorder/preview', { params: { project } }).then(r => r.data),
}
