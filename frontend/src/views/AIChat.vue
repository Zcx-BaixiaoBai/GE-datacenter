<template>
  <div class="chat-page">
    <!-- 消息列表 -->
    <div class="chat-messages" ref="msgBox">
      <div class="chat-welcome" v-if="!messages.length">
        <Icon name="activity" :size="32" />
        <h3>AI 数据助手</h3>
        <p>我可以查询和分析电表、安全、设备、预算等数据</p>
        <div class="chat-suggestions">
          <button v-for="s in suggestions" :key="s" class="suggestion-btn" @click="sendQuick(s)">{{ s }}</button>
        </div>
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="msg-item" :class="msg.role">
        <div class="msg-avatar">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
        <div class="msg-content" v-html="formatMsg(msg.content)"></div>
      </div>
      <div v-if="thinking" class="msg-item assistant">
        <div class="msg-avatar">AI</div>
        <div class="msg-content thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input-area">
      <textarea
        v-model="input" class="chat-input" placeholder="输入问题..."
        @keydown.enter.exact.prevent="send" rows="1" ref="inputRef"
      ></textarea>
      <button class="chat-send" @click="send" :disabled="!input || thinking">
        <Icon name="zap" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import Icon from '../components/Icon.vue'
import api from '../api'

const messages = ref([])
const input = ref('')
const thinking = ref(false)
const msgBox = ref(null)
const inputRef = ref(null)

const suggestions = [
  '哪个项目电表故障最多？',
  '安全隐患逾期情况如何？',
  '设备通讯故障率最高的项目',
  '预算执行情况总览',
]

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

  // 构建历史
  const history = messages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content }))

  try {
    const result = await api.aiChat(msg, history)
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
.chat-page { display: flex; flex-direction: column; height: calc(100vh - 44px); }
.chat-messages { flex: 1; overflow-y: auto; padding: 20px 24px; }
.chat-welcome { text-align: center; padding: 60px 20px; color: var(--text-2); }
.chat-welcome h3 { margin: 12px 0 4px; color: var(--text-1); }
.chat-welcome p { font-size: 13px; margin-bottom: 20px; }
.chat-suggestions { display: flex; flex-direction: column; gap: 8px; max-width: 400px; margin: 0 auto; }
.suggestion-btn {
  padding: 10px 16px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-card); color: var(--text-1); font-size: 13px; cursor: pointer; transition: all 0.15s;
}
.suggestion-btn:hover { border-color: var(--accent); color: var(--accent); }

.msg-item { display: flex; gap: 10px; margin-bottom: 16px; }
.msg-avatar {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
}
.msg-item.user .msg-avatar { background: var(--accent); color: #fff; }
.msg-item.assistant .msg-avatar { background: var(--border); color: var(--text-1); }
.msg-content {
  background: var(--bg-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: 10px 14px; font-size: 13px; line-height: 1.6;
  max-width: 80%; color: var(--text-1);
}
.msg-item.user .msg-content { background: rgba(9,105,218,.06); border-color: rgba(9,105,218,.15); }
.msg-content.thinking { display: flex; gap: 4px; align-items: center; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); animation: pulse 1.4s infinite; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes pulse { 0%, 80%, 100% { opacity: .3; } 40% { opacity: 1; } }

.chat-input-area { display: flex; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--border); background: var(--bg-card); }
.chat-input {
  flex: 1; padding: 10px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-page); color: var(--text-1); font-size: 13px; resize: none; outline: none;
  font-family: inherit; transition: border-color 0.15s;
}
.chat-input:focus { border-color: var(--accent); }
.chat-send {
  padding: 0 16px; border: none; border-radius: var(--radius-sm);
  background: var(--accent); color: #fff; cursor: pointer; transition: opacity 0.15s;
  display: flex; align-items: center; justify-content: center;
}
.chat-send:disabled { opacity: .4; cursor: not-allowed; }
</style>
