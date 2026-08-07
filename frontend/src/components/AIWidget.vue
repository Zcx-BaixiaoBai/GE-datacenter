<template>
  <!-- 浮球 -->
  <div
    v-show="!panelOpen"
    class="ai-ball"
    :style="{ left: ballPos.x + 'px', top: ballPos.y + 'px' }"
    @mousedown.prevent="onBallDragStart"
    @click="onBallClick"
  >
    <Icon name="activity" :size="22" />
    <span v-if="hasUnread" class="ai-ball-dot"></span>
  </div>

  <!-- 浮窗 -->
  <div
    v-if="panelOpen"
    class="ai-panel"
    :style="{ left: panelPos.x + 'px', top: panelPos.y + 'px', width: panelSize.w + 'px', height: panelSize.h + 'px' }"
  >
    <!-- 标题栏(可拖动) -->
    <div class="ai-panel-header" @mousedown.prevent="onPanelDragStart">
      <span class="ai-panel-title">
        <Icon name="activity" :size="14" />
        AI 数据助手
      </span>
      <button class="ai-panel-close" @click="panelOpen = false">
        <Icon name="x" :size="14" />
      </button>
    </div>

    <!-- 消息区 -->
    <div class="ai-panel-messages" ref="msgBox">
      <div v-if="!messages.length" class="ai-panel-welcome">
        <p>可查询电表、安全、设备、预算等数据</p>
        <div class="ai-panel-suggestions">
          <button v-for="s in suggestions" :key="s" @click="sendQuick(s)">{{ s }}</button>
        </div>
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="msg.role">
        <div class="ai-msg-avatar">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
        <div class="ai-msg-text" v-html="formatMsg(msg.content)"></div>
      </div>
      <div v-if="thinking" class="ai-msg assistant">
        <div class="ai-msg-avatar">AI</div>
        <div class="ai-msg-text thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="ai-panel-input">
      <textarea
        v-model="input" placeholder="输入问题..." rows="1"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button class="ai-send-btn" @click="send" :disabled="!input || thinking">
        <Icon name="zap" :size="14" />
      </button>
    </div>

    <!-- 拖拽调整大小手柄 -->
    <div class="ai-panel-resize" @mousedown.prevent="onResizeStart"></div>
  </div>
</template>

<script setup>
import { ref, nextTick, reactive } from 'vue'
import Icon from './Icon.vue'
import api from '../api'

const panelOpen = ref(false)
const hasUnread = ref(false)
const messages = ref([])
const input = ref('')
const thinking = ref(false)
const msgBox = ref(null)

const ballPos = reactive({ x: window.innerWidth - 70, y: window.innerHeight - 70 })
const panelPos = reactive({ x: window.innerWidth - 420, y: 80 })
const panelSize = reactive({ w: 380, h: 520 })

const suggestions = [
  '哪个项目电表故障最多？',
  '安全隐患逾期情况',
  '设备通讯故障率最高项目',
  '预算执行总览',
]

// ─── 浮球拖拽 ───
let ballDragging = false
let ballMoved = false
let ballStart = { x: 0, y: 0, ox: 0, oy: 0 }

function onBallDragStart(e) {
  ballDragging = true
  ballMoved = false
  ballStart = { x: e.clientX, y: e.clientY, ox: ballPos.x, oy: ballPos.y }
  document.addEventListener('mousemove', onBallDragMove)
  document.addEventListener('mouseup', onBallDragEnd)
}

function onBallDragMove(e) {
  if (!ballDragging) return
  const dx = e.clientX - ballStart.x
  const dy = e.clientY - ballStart.y
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) ballMoved = true
  ballPos.x = Math.max(0, Math.min(window.innerWidth - 48, ballStart.ox + dx))
  ballPos.y = Math.max(0, Math.min(window.innerHeight - 48, ballStart.oy + dy))
}

function onBallDragEnd() {
  ballDragging = false
  document.removeEventListener('mousemove', onBallDragMove)
  document.removeEventListener('mouseup', onBallDragEnd)
}

function onBallClick() {
  if (ballMoved) return // 拖动不触发点击
  panelOpen.value = !panelOpen.value
  hasUnread.value = false
}

// ─── 浮窗拖拽 ───
let panelDragging = false
let panelStart = { x: 0, y: 0, ox: 0, oy: 0 }

function onPanelDragStart(e) {
  panelDragging = true
  panelStart = { x: e.clientX, y: e.clientY, ox: panelPos.x, oy: panelPos.y }
  document.addEventListener('mousemove', onPanelDragMove)
  document.addEventListener('mouseup', onPanelDragEnd)
}

function onPanelDragMove(e) {
  if (!panelDragging) return
  panelPos.x = Math.max(0, Math.min(window.innerWidth - panelSize.w, panelStart.ox + e.clientX - panelStart.x))
  panelPos.y = Math.max(0, Math.min(window.innerHeight - 40, panelStart.oy + e.clientY - panelStart.y))
}

function onPanelDragEnd() {
  panelDragging = false
  document.removeEventListener('mousemove', onPanelDragMove)
  document.removeEventListener('mouseup', onPanelDragEnd)
}

// ─── 浮窗调整大小 ───
let resizing = false
let resizeStart = { x: 0, y: 0, w: 0, h: 0 }

function onResizeStart(e) {
  resizing = true
  resizeStart = { x: e.clientX, y: e.clientY, w: panelSize.w, h: panelSize.h }
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
}

function onResizeMove(e) {
  if (!resizing) return
  panelSize.w = Math.max(280, resizeStart.w + e.clientX - resizeStart.x)
  panelSize.h = Math.max(360, resizeStart.h + e.clientY - resizeStart.y)
}

function onResizeEnd() {
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
}

// ─── 对话 ───
function formatMsg(text) {
  if (!text) return ''
  return text.replace(/\n/g, '<br>')
}

async function sendQuick(q) {
  input.value = q
  await send()
}

async function send() {
  const msg = input.value.trim()
  if (!msg || thinking.value) return
  messages.value.push({ role: 'user', content: msg })
  input.value = ''
  thinking.value = true
  await scrollBottom()

  const history = messages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content }))
  try {
    const result = await api.aiChat(msg, history, 'web_float_ball')
    thinking.value = false
    if (result.error) {
      messages.value.push({ role: 'assistant', content: '[错误] ' + result.error })
      if (result.config_needed) {
        messages.value.push({ role: 'assistant', content: '请在「管理设置」中配置 AI 的 URL、API Key 和模型名称。' })
      }
    } else {
      messages.value.push({ role: 'assistant', content: result.reply })
    }
  } catch (e) {
    thinking.value = false
    messages.value.push({ role: 'assistant', content: '[网络错误] ' + (e.message || '请求失败') })
  }
  await scrollBottom()
}

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}
</script>

<style scoped>
/* ─── 浮球 ─── */
.ai-ball {
  position: fixed; z-index: 9999;
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--accent); color: #fff;
  display: flex; align-items: center; justify-content: center;
  cursor: grab; user-select: none;
  box-shadow: 0 2px 12px rgba(9,105,218,.35);
  transition: transform 0.15s, box-shadow 0.15s;
}
.ai-ball:hover { transform: scale(1.08); box-shadow: 0 4px 16px rgba(9,105,218,.45); }
.ai-ball:active { cursor: grabbing; }
.ai-ball-dot {
  position: absolute; top: 2px; right: 2px;
  width: 8px; height: 8px; border-radius: 50%;
  background: #f85149; border: 1.5px solid #fff;
}

/* ─── 浮窗 ─── */
.ai-panel {
  position: fixed; z-index: 9999;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,.12);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.ai-panel-header {
  height: 38px; flex-shrink: 0;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border-subtle);
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 12px; cursor: grab; user-select: none;
}
.ai-panel-header:active { cursor: grabbing; }
.ai-panel-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: var(--text-1); }
.ai-panel-close { background: none; border: none; cursor: pointer; color: var(--text-3); padding: 4px; border-radius: 4px; display: flex; }
.ai-panel-close:hover { color: var(--red); background: rgba(207,34,46,.08); }

.ai-panel-messages { flex: 1; overflow-y: auto; padding: 12px; }
.ai-panel-welcome { text-align: center; padding: 20px 8px; color: var(--text-3); font-size: 12px; }
.ai-panel-suggestions { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.ai-panel-suggestions button {
  padding: 7px 10px; border: 1px solid var(--border-subtle); border-radius: 6px;
  background: var(--bg-card); color: var(--text-2); font-size: 12px; cursor: pointer; transition: all 0.12s;
}
.ai-panel-suggestions button:hover { border-color: var(--accent); color: var(--accent); }

.ai-msg { display: flex; gap: 8px; margin-bottom: 10px; }
.ai-msg-avatar {
  width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600;
}
.ai-msg.user .ai-msg-avatar { background: var(--accent); color: #fff; }
.ai-msg.assistant .ai-msg-avatar { background: var(--border); color: var(--text-1); }
.ai-msg-text {
  background: var(--bg-hover); border-radius: 8px; padding: 8px 10px;
  font-size: 12px; line-height: 1.5; max-width: 85%; color: var(--text-1);
  word-break: break-word;
}
.ai-msg.user .ai-msg-text { background: rgba(9,105,218,.08); }
.ai-msg-text.thinking { display: flex; gap: 4px; align-items: center; }
.dot { width: 5px; height: 5px; border-radius: 50%; background: var(--text-3); animation: pulse 1.4s infinite; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes pulse { 0%, 80%, 100% { opacity: .3; } 40% { opacity: 1; } }

.ai-panel-input { flex-shrink: 0; display: flex; gap: 6px; padding: 8px 10px; border-top: 1px solid var(--border-subtle); }
.ai-panel-input textarea {
  flex: 1; padding: 6px 10px; border: 1px solid var(--border-subtle); border-radius: 6px;
  background: var(--bg-page); color: var(--text-1); font-size: 12px; resize: none; outline: none;
  font-family: inherit; transition: border-color 0.12s; max-height: 80px;
}
.ai-panel-input textarea:focus { border-color: var(--accent); }
.ai-send-btn {
  padding: 0 10px; border: none; border-radius: 6px;
  background: var(--accent); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: opacity 0.12s;
}
.ai-send-btn:disabled { opacity: .4; cursor: not-allowed; }

.ai-panel-resize {
  position: absolute; bottom: 0; right: 0;
  width: 16px; height: 16px; cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, var(--border) 50%);
}
</style>
