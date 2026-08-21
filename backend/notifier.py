"""
金鹰集团数据管理中心 - 独立通知推送模块
不依赖 QwenPaw, 直接调用微信 iLink Bot API 和飞书 Open API

微信 iLink Bot:
  1. 扫码登录获取 bot_token
  2. 用户需先发一条消息给 bot (获取 context_token)
  3. 之后可向该用户推送消息

飞书:
  1. 管理员配置 app_id + app_secret
  2. 直接调用 Open API 主动推送
"""
import os
import json
import base64
import secrets
import time
import tempfile
import threading
import requests
import segno
from datetime import datetime

from db import get_conn

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'notify_config.json')
WECHAT_TOKEN_FILE = os.path.join(DATA_DIR, 'wechat_token.json')
WECHAT_USERS_FILE = os.path.join(DATA_DIR, 'wechat_users.json')
# 推送状态持久化(重启后恢复, 避免重复推送/漏推)
SEND_STATE_FILE = os.path.join(DATA_DIR, 'send_state.json')

ILINK_BASE = "https://ilinkai.weixin.qq.com"
FEISHU_BASE = "https://open.feishu.cn"

DEFAULT_CONFIG = {
    "enabled": False,
    "daily_time": "09:00",
    "projects": {},
    "feishu": {"app_id": "", "app_secret": ""},
}

_notify_logs = []
_scheduler_running = False
_scheduler_thread = None
_last_send_date = None


def _save_send_state():
    """持久化推送状态(重启后恢复, 避免重复推送/漏推)"""
    global _last_send_date
    try:
        with open(SEND_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_send_date': _last_send_date,
                       'saved_at': datetime.now().isoformat()}, f, ensure_ascii=False)
    except Exception:
        pass

# 飞书 token 缓存
_feishu_token = None
_feishu_token_time = 0


def _load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    _save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def _save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_config():
    return _load_config()


def update_config(new_cfg):
    cfg = _load_config()
    for key in ['enabled', 'daily_time']:
        if key in new_cfg:
            cfg[key] = new_cfg[key]
    if 'feishu' in new_cfg:
        cfg['feishu'] = new_cfg['feishu']
    _save_config(cfg)
    return cfg


def set_project_config(project_name, channel, target_user, target_session, enabled=True):
    cfg = _load_config()
    if 'projects' not in cfg:
        cfg['projects'] = {}
    cfg['projects'][project_name] = {
        'channel': channel,
        'target_user': target_user,
        'target_session': target_session,
        'enabled': enabled,
    }
    _save_config(cfg)
    return cfg['projects'][project_name]


def delete_project_config(project_name):
    cfg = _load_config()
    cfg.get('projects', {}).pop(project_name, None)
    _save_config(cfg)


def _add_log(project, status, msg):
    t = datetime.now().strftime('%H:%M:%S')
    entry = {'time': t, 'date': datetime.now().strftime('%Y-%m-%d'),
             'project': project, 'status': status, 'msg': msg}
    _notify_logs.append(entry)
    if len(_notify_logs) > 200:
        _notify_logs[:] = _notify_logs[-100:]
    # 持久化到独立的日志文件, 不碰配置文件
    try:
        import json as _json
        log_file = os.path.join(DATA_DIR, 'notify_logs.json')
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = _json.load(f)
        logs.append(entry)
        if len(logs) > 500:
            logs[:] = logs[-300:]
        with open(log_file, 'w', encoding='utf-8') as f:
            _json.dump(logs, f, ensure_ascii=False)
    except Exception:
        pass


def get_logs(limit=50):
    """读取推送日志(重启不丢历史): 合并文件持久化历史 + 内存增量, 按时间去重"""
    import json as _json
    log_file = os.path.join(DATA_DIR, 'notify_logs.json')
    file_logs = []
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                file_logs = _json.load(f) or []
    except Exception:
        pass
    # 合并: 文件历史在前, 内存增量在后; 用 (date,time,project,msg) 去重
    merged = list(file_logs)
    seen = set()
    for e in merged:
        seen.add((e.get('date', ''), e.get('time', ''), e.get('project', ''), e.get('msg', '')))
    for e in _notify_logs:
        k = (e.get('date', ''), e.get('time', ''), e.get('project', ''), e.get('msg', ''))
        if k not in seen:
            merged.append(e)
            seen.add(k)
    # 最新的在前
    return list(reversed(merged[-limit:])) if merged else []


# ─── 微信 iLink Bot ─────────────────────────────────

def _make_ilink_headers(bot_token=''):
    """构造 iLink API 请求头"""
    uin = secrets.randbelow(0xFFFFFFFF)
    uin_b64 = base64.b64encode(str(uin).encode()).decode()
    headers = {
        'Content-Type': 'application/json',
        'AuthorizationType': 'ilink_bot_token',
        'X-WECHAT-UIN': uin_b64,
    }
    if bot_token:
        headers['Authorization'] = f'Bearer {bot_token}'
    return headers


def _load_wechat_token():
    if os.path.exists(WECHAT_TOKEN_FILE):
        try:
            with open(WECHAT_TOKEN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_wechat_token(token_data):
    with open(WECHAT_TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)


def _load_wechat_users():
    if os.path.exists(WECHAT_USERS_FILE):
        try:
            with open(WECHAT_USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_wechat_users(users):
    with open(WECHAT_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def wechat_get_qrcode():
    """获取微信登录二维码"""
    try:
        resp = requests.get(
            f'{ILINK_BASE}/ilink/bot/get_bot_qrcode',
            params={'bot_type': 3},
            headers=_make_ilink_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        qrcode = data.get('qrcode', '')
        qrcode_img_content = data.get('qrcode_img_content', '')

        # 构造扫码URL (参考QwenPaw逻辑)
        if qrcode_img_content and qrcode_img_content.startswith('http'):
            scan_url = qrcode_img_content
        elif qrcode:
            scan_url = f'{ILINK_BASE}/ilink/bot/confirm_login?qrcode={qrcode}&bot_type=3'
        else:
            return {'error': 'iLink API 返回数据不完整'}

        # 用 segno 从 scan_url 生成二维码图片
        import io
        qr = segno.make(scan_url, error='M')
        buf = io.BytesIO()
        qr.save(buf, kind='png', scale=6, border=2)
        qrcode_img = base64.b64encode(buf.getvalue()).decode()

        _add_log('wechat', 'info', f'获取二维码成功, scan_url={scan_url[:40]}')
        return {'qrcode_img': qrcode_img, 'poll_token': qrcode}
    except Exception as e:
        _add_log('wechat', 'error', f'获取二维码失败: {str(e)[:80]}')
        return {'error': str(e)}


def wechat_poll_status(qrcode_key):
    """轮询微信扫码状态"""
    try:
        resp = requests.get(
            f'{ILINK_BASE}/ilink/bot/get_qrcode_status',
            params={'qrcode': qrcode_key},
            headers=_make_ilink_headers(),
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get('status', 'waiting')

        if status == 'confirmed':
            bot_token = data.get('bot_token', '')
            base_url = data.get('baseurl', ILINK_BASE)
            _save_wechat_token({'bot_token': bot_token, 'base_url': base_url,
                                 'login_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            _add_log('wechat', 'success', '微信扫码登录成功, bot_token已保存')
            # 登录成功后立即启动消息轮询线程
            _start_wechat_poller()

        return {'status': status, 'confirmed': status == 'confirmed'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)[:100]}


# ─── 微信消息轮询 (获取context_token + AI对话) ─────────────────────────────────

_wechat_poller_thread = None
_wechat_poller_running = False

def _start_wechat_poller():
    """启动微信消息轮询线程"""
    global _wechat_poller_thread, _wechat_poller_running
    if _wechat_poller_running:
        return
    _wechat_poller_running = True
    _wechat_poller_thread = threading.Thread(target=_wechat_poll_loop, daemon=True)
    _wechat_poller_thread.start()
    _add_log('wechat', 'info', '微信消息轮询线程已启动')

def _stop_wechat_poller():
    global _wechat_poller_running
    _wechat_poller_running = False

# ─── 消息去重 (防止重复处理旧消息) ─────────────────────────────────

_processed_msg_ids = set()
_PROCESSED_MAX = 500  # 最多记住500条已处理消息ID

def _is_processed(msg_id):
    """检查消息是否已处理过"""
    if msg_id in _processed_msg_ids:
        return True
    _processed_msg_ids.add(msg_id)
    if len(_processed_msg_ids) > _PROCESSED_MAX:
        # 截断: 保留最近的一半
        _processed.clear()
        _processed_msg_ids.clear()
    return False


def _wechat_poll_loop():
    """轮询微信消息, 获取context_token, 并转发AI回复"""
    global _wechat_poller_running
    import uuid as _uuid
    _add_log('wechat', 'info', '微信消息轮询循环开始')

    while _wechat_poller_running:
        try:
            token_data = _load_wechat_token()
            bot_token = token_data.get('bot_token', '')
            base_url = token_data.get('base_url', ILINK_BASE)

            if not bot_token:
                time.sleep(30)
                continue

            uin = secrets.randbelow(0xFFFFFFFF)
            uin_b64 = base64.b64encode(str(uin).encode()).decode()
            headers = {
                'Content-Type': 'application/json',
                'AuthorizationType': 'ilink_bot_token',
                'X-WECHAT-UIN': uin_b64,
                'Authorization': f'Bearer {bot_token}',
            }
            body = {'get_updates_buf': '', 'base_info': {'channel_version': '2.0.1'}}

            resp = requests.post(
                f'{base_url}/ilink/bot/getupdates',
                json=body, headers=headers, timeout=40,
            )
            data = resp.json()
            msgs = data.get('msgs', [])

            for m in msgs:
                # 消息去重: 用 message_id 或 context_token 作为唯一标识
                msg_id = str(m.get('message_id', '') or m.get('context_token', ''))
                if not msg_id or _is_processed(msg_id):
                    continue

                from_uid = m.get('from_user_id', '')
                ctx_token = m.get('context_token', '')

                # 只处理 message_type=1 的用户消息, 跳过 bot 自己发的消息
                if m.get('message_type', 0) != 1:
                    continue

                # 保存/更新用户的context_token
                if from_uid and ctx_token:
                    users = _load_wechat_users()
                    is_new = from_uid not in users
                    users[from_uid] = {
                        'channel': 'wechat',
                        'name': users.get(from_uid, {}).get('name', from_uid[:15]),
                        'context_token': ctx_token,
                        'active': True,
                    }
                    _save_wechat_users(users)
                    if is_new:
                        _add_log('wechat', 'info', f'新微信用户: {from_uid[:15]}...')

                # 提取消息文本
                text = ''
                item_list = m.get('item_list', [])
                for item in item_list:
                    if item.get('type') == 1:
                        text = item.get('text_item', {}).get('text', '')
                        break

                if text and from_uid and ctx_token:
                    _add_log('wechat', 'info', f'收到微信消息: {text[:30]}... from {from_uid[:15]}...')
                    try:
                        from ai import chat
                        result = chat(text, [], user_id=from_uid)
                        if result.get('error'):
                            reply = f'[AI错误] {result["error"]}'
                        else:
                            reply = result.get('reply', '抱歉, 我无法回答。')

                        # 发送AI回复
                        ok, send_msg = _wechat_send_message(from_uid, reply)
                        _add_log('wechat', 'success' if ok else 'error', f'AI回复: {send_msg}')
                    except Exception as e:
                        _add_log('wechat', 'error', f'AI处理失败: {str(e)[:80]}')

            time.sleep(3)
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            _add_log('wechat', 'error', f'微信轮询异常: {str(e)[:80]}')
            time.sleep(10)


def wechat_get_user_info():
    """获取已绑定的用户信息(微信+飞书统一存储)"""
    token_data = _load_wechat_token()
    users = _load_wechat_users()
    result = {
        'logged_in': bool(token_data.get('bot_token')),
        'login_time': token_data.get('login_time', ''),
        'poller_active': _wechat_poller_running,
        'feishu_bound': bool(_load_feishu_creds().get('app_id')),
        'feishu_bind_time': _load_feishu_creds().get('bind_time', ''),
        'users': [],
    }
    for uid, info in users.items():
        channel = info.get('channel', 'wechat')
        result['users'].append({
            'user_id': uid,
            'name': info.get('name', uid[:20]),
            'channel': channel,
            'context_token': info.get('context_token', ''),
            'active': info.get('active', False) if channel == 'wechat' else True,
        })
    return result


def feishu_handle_webhook(event_data):
    """处理飞书 webhook 事件 (备用, 优先用 WebSocket)"""
    if 'challenge' in event_data:
        return {'challenge': event_data['challenge']}
    _feishu_process_message(event_data)
    return {'ok': True}


def _feishu_process_message(event_data):
    """统一的飞书消息处理: 解析消息 -> AI回复 -> 发送"""
    header = event_data.get('header', {})
    event = event_data.get('event', {})

    msg = event.get('message', {})
    if not msg:
        return

    # 消息去重
    msg_id = msg.get('message_id', '')
    if msg_id and _is_processed(msg_id):
        return

    msg_type = msg.get('message_type', '')
    if msg_type != 'text':
        return

    import json as _json
    content_str = msg.get('content', '{}')
    try:
        content = _json.loads(content_str)
        user_text = content.get('text', '').strip()
    except:
        user_text = ''
    if not user_text:
        return

    sender = msg.get('sender', {})
    sender_id = sender.get('sender_id', {})
    open_id = sender_id.get('open_id', '')
    if not open_id or not open_id.startswith('ou_'):
        creds = _load_feishu_creds()
        open_id = creds.get('open_id', '')
    if not open_id:
        return

    _add_log('feishu', 'info', f'收到飞书消息: {user_text[:30]}... from {open_id[:15]}...')

    users = _load_wechat_users()
    if open_id not in users:
        users[open_id] = {'channel': 'feishu', 'name': f'飞书用户_{open_id[:8]}', 'context_token': 'feishu_active', 'active': True}
        _save_wechat_users(users)

    try:
        from ai import chat
        result = chat(user_text, [], user_id=open_id)
        reply = result.get('reply', '') or f'[AI错误] {result.get("error", "")}'
        ok, send_msg = _feishu_send_message(open_id, reply)
        _add_log('feishu', 'success' if ok else 'error', f'AI回复: {send_msg}')
    except Exception as e:
        _add_log('feishu', 'error', f'AI处理失败: {str(e)[:80]}')


# ─── 飞书 WebSocket 长连接 (不需要公网IP) ─────────────────────────────────

_feishu_ws_thread = None
_feishu_ws_running = False

def _start_feishu_ws():
    """启动飞书 WebSocket 长连接线程"""
    global _feishu_ws_thread, _feishu_ws_running
    if _feishu_ws_running:
        return '飞书WebSocket已在运行'
    creds = _load_feishu_creds()
    if not creds.get('app_id'):
        return '飞书未绑定, 请先扫码'
    _feishu_ws_running = True
    _feishu_ws_thread = threading.Thread(target=_feishu_ws_loop, daemon=True)
    _feishu_ws_thread.start()
    _add_log('feishu', 'info', '飞书WebSocket线程已启动')
    return '飞书WebSocket已启动'

def _stop_feishu_ws():
    global _feishu_ws_running
    _feishu_ws_running = False

def _feishu_ws_loop():
    """飞书 WebSocket 长连接循环 - 接收消息事件, 转发AI回复"""
    global _feishu_ws_running
    import asyncio
    _add_log('feishu', 'info', '飞书WebSocket循环开始')

    while _feishu_ws_running:
        try:
            creds = _load_feishu_creds()
            app_id = creds.get('app_id', '')
            app_secret = creds.get('app_secret', '')
            if not app_id or not app_secret:
                time.sleep(30)
                continue

            _add_log('feishu', 'info', f'飞书WebSocket连接中... app_id={app_id[:15]}...')

            # 用 lark-oapi WebSocket 接收事件
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

            def on_message_receive(data: P2ImMessageReceiveV1) -> None:
                try:
                    msg = data.event.message
                    # 消息去重
                    msg_id = msg.message_id
                    if msg_id and _is_processed(msg_id):
                        return

                    # 只处理用户消息, 跳过bot自己发的
                    msg_type = msg.message_type
                    if msg_type != 'text':
                        return
                    content_str = msg.content
                    sender_id = data.event.sender.sender_id
                    open_id = sender_id.open_id

                    import json as _json2
                    content = _json2.loads(content_str)
                    user_text = content.get('text', '').strip()
                    if not user_text:
                        return

                    _add_log('feishu', 'info', f'WS收到飞书消息: {user_text[:30]}... from {open_id[:15]}...')

                    users = _load_wechat_users()
                    if open_id not in users:
                        users[open_id] = {'channel': 'feishu', 'name': f'飞书用户_{open_id[:8]}', 'context_token': 'feishu_active', 'active': True}
                        _save_wechat_users(users)

                    from ai import chat
                    result = chat(user_text, [], user_id=open_id)
                    reply = result.get('reply', '') or f'[AI错误] {result.get("error", "")}'
                    ok, send_msg = _feishu_send_message(open_id, reply)
                    _add_log('feishu', 'success' if ok else 'error', f'WS AI回复: {send_msg}')
                except Exception as e:
                    _add_log('feishu', 'error', f'WS消息处理失败: {str(e)[:80]}')

            event_handler = (
                lark.EventDispatcherHandler.builder('', '')
                .register_p2_im_message_receive_v1(on_message_receive)
                .build()
            )

            ws_client = lark.ws.Client(
                app_id,
                app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO,
            )

            # WebSocket 连接 (阻塞, 直到断开)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ws_client = lark.ws.Client(
                app_id,
                app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO,
            )
            # 用 start() 阻塞运行 (内部自动连接+ping+重连)
            ws_client.start()

        except Exception as e:
            if not _feishu_ws_running:
                break
            _add_log('feishu', 'error', f'WebSocket异常: {str(e)[:80]}')
            time.sleep(5)


def _wechat_send_message(to_user_id, text):
    """通过 iLink API 发送微信消息"""
    token_data = _load_wechat_token()
    bot_token = token_data.get('bot_token', '')
    base_url = token_data.get('base_url', ILINK_BASE)

    if not bot_token:
        return False, '微信未登录, 请先扫码'

    users = _load_wechat_users()
    user_info = users.get(to_user_id, {})
    context_token = user_info.get('context_token', '')

    if not context_token:
        return False, '用户未激活: 该用户需要先发一条消息给bot'

    import uuid
    msg = {
        'from_user_id': '',
        'to_user_id': to_user_id,
        'client_id': str(uuid.uuid4()),
        'message_type': 2,
        'message_state': 2,
        'context_token': context_token,
        'item_list': [{'type': 1, 'text_item': {'text': text}}],
    }

    try:
        resp = requests.post(
            f'{base_url}/ilink/bot/sendmessage',
            json={'msg': msg, 'base_info': {'channel_version': '2.0.1'}},
            headers=_make_ilink_headers(bot_token),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        ret = data.get('ret', 0)
        errcode = data.get('errcode', 0)
        if ret == 0 and errcode == 0:
            return True, '微信推送成功'
        elif ret == -2:
            return False, 'context_token已失效, 请让用户重新发一条消息给bot'
        else:
            return False, f'微信推送失败: ret={ret} errcode={errcode}'
    except Exception as e:
        return False, f'微信推送异常: {str(e)[:80]}'


# ─── 飞书 Open API (扫码绑定, 不需手动配置) ─────────────────────────────────

FEISHU_ACCOUNTS = "https://accounts.feishu.cn"
FEISHU_REGISTER = "/oauth/v1/app/registration"
FEISHU_OPEN = "https://open.feishu.cn"

_feishu_token = None
_feishu_token_time = 0

FEISHU_CREDS_FILE = os.path.join(DATA_DIR, 'feishu_creds.json')


def _load_feishu_creds():
    if os.path.exists(FEISHU_CREDS_FILE):
        try:
            with open(FEISHU_CREDS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_feishu_creds(creds):
    with open(FEISHU_CREDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)


def feishu_get_qrcode():
    """飞书扫码绑定 - Device Authorization Grant 流程"""
    from urllib.parse import urlencode
    try:
        # Step 1: init
        resp = requests.post(
            f'{FEISHU_ACCOUNTS}{FEISHU_REGISTER}',
            data=urlencode({'action': 'init'}),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15,
        )
        resp.raise_for_status()
        methods = resp.json().get('supported_auth_methods', [])
        if 'client_secret' not in methods:
            return {'error': '飞书不支持 client_secret 认证'}

        # Step 2: begin
        resp = requests.post(
            f'{FEISHU_ACCOUNTS}{FEISHU_REGISTER}',
            data=urlencode({
                'action': 'begin',
                'archetype': 'PersonalAgent',
                'auth_method': 'client_secret',
                'request_user_info': 'open_id',
            }),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        device_code = data.get('device_code', '')
        verification_uri = data.get('verification_uri_complete', '')

        if not device_code or not verification_uri:
            return {'error': '飞书返回数据不完整'}

        # 生成二维码图片
        qr = segno.make(verification_uri, error='M')
        import io
        buf = io.BytesIO()
        qr.save(buf, kind='png', scale=6, border=2)
        qrcode_img = base64.b64encode(buf.getvalue()).decode()

        _add_log('feishu', 'info', f'飞书二维码生成成功, device_code={device_code[:20]}')
        return {'qrcode_img': qrcode_img, 'poll_token': device_code}
    except Exception as e:
        _add_log('feishu', 'error', f'飞书二维码获取失败: {str(e)[:80]}')
        return {'error': str(e)}


def feishu_poll_status(device_code):
    """轮询飞书扫码状态"""
    from urllib.parse import urlencode
    try:
        resp = requests.post(
            f'{FEISHU_ACCOUNTS}{FEISHU_REGISTER}',
            data=urlencode({'action': 'poll', 'device_code': device_code}),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        data = resp.json()

        # 成功: 返回 client_id, client_secret, open_id
        if data.get('client_id') and data.get('client_secret'):
            user_info = data.get('user_info', {})
            open_id = user_info.get('open_id', '')
            creds = {
                'app_id': data['client_id'],
                'app_secret': data['client_secret'],
                'open_id': open_id,
                'tenant_brand': user_info.get('tenant_brand', 'feishu'),
                'bind_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            _save_feishu_creds(creds)

            # 同时存入已绑定用户列表
            if open_id:
                users = _load_wechat_users()
                users[open_id] = {
                    'channel': 'feishu',
                    'name': user_info.get('tenant_brand', '飞书用户'),
                    'context_token': 'feishu_active',
                    'active': True,
                }
                _save_wechat_users(users)

            _add_log('feishu', 'success', '飞书扫码绑定成功, 凭证已保存, 用户已记录')
            # 绑定成功后立即启动 WebSocket 长连接
            _start_feishu_ws()
            return {'status': 'confirmed', 'confirmed': True}

        # 错误处理
        error = data.get('error', '')
        if error in ('expired_token', 'invalid_grant'):
            return {'status': 'expired', 'confirmed': False}
        if error == 'access_denied':
            return {'status': 'denied', 'confirmed': False}
        return {'status': 'waiting', 'confirmed': False}
    except Exception as e:
        return {'status': 'error', 'error': str(e)[:100]}


def feishu_get_status():
    """获取飞书绑定状态"""
    creds = _load_feishu_creds()
    return {
        'bound': bool(creds.get('app_id')),
        'bind_time': creds.get('bind_time', ''),
        'open_id': creds.get('open_id', '')[:20] + '...' if creds.get('open_id') else '',
    }


def _get_feishu_token():
    """获取飞书 tenant_access_token (缓存1小时)"""
    global _feishu_token, _feishu_token_time

    if _feishu_token and time.time() - _feishu_token_time < 3600:
        return _feishu_token

    creds = _load_feishu_creds()
    app_id = creds.get('app_id', '')
    app_secret = creds.get('app_secret', '')

    if not app_id or not app_secret:
        return None

    try:
        resp = requests.post(
            f'{FEISHU_OPEN}/open-apis/auth/v3/tenant_access_token/internal',
            json={'app_id': app_id, 'app_secret': app_secret},
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get('tenant_access_token', '')
        if token:
            _feishu_token = token
            _feishu_token_time = time.time()
            return token
    except Exception as e:
        _add_log('feishu', 'error', f'获取token失败: {str(e)[:80]}')
    return None


def _feishu_send_message(open_id, text):
    """通过飞书 Open API 发送消息"""
    token = _get_feishu_token()
    if not token:
        return False, '飞书未绑定或token获取失败'

    # 如果 target_user 是 "self", 用绑定时获取的 open_id
    if open_id == 'self':
        creds = _load_feishu_creds()
        open_id = creds.get('open_id', '')
        if not open_id:
            return False, '飞书未获取到用户 open_id'

    try:
        resp = requests.post(
            f'{FEISHU_OPEN}/open-apis/im/v1/messages?receive_id_type=open_id',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={
                'receive_id': open_id,
                'msg_type': 'text',
                'content': json.dumps({'text': text}),
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 0:
            return True, '飞书推送成功'
        return False, f'飞书推送失败: {data.get("msg", "")}'
    except Exception as e:
        return False, f'飞书推送异常: {str(e)[:80]}'


# ─── 统一发送入口 ─────────────────────────────────

def _build_project_message(project_name, data):
    """构建项目日报消息 — 三系统必显示，底部附 datacenter 链接"""
    lines = [f'{project_name} - 管理数据日报', datetime.now().strftime('%Y-%m-%d %H:%M'), '']

    # ── 瑞信电表 ──
    m = data.get('meters') or {}
    lines.append('【瑞信电表】')
    lines.append(f"总表具: {m.get('total', 0)}块")
    lines.append(f"故障: {m.get('fault', 0)}块 (故障率{m.get('fault_rate', 0)*100:.2f}%)")
    if m.get('offline', 0) > 0:
        lines.append(f"⚠离线 {m['offline']}块")
    if m.get('abnormal', 0) > 0:
        lines.append(f"⚠异常送电 {m['abnormal']}块")
    if m.get('unpaid', 0) > 0:
        lines.append(f"⚠无签呈后付费 {m['unpaid']}块")
    lines.append(f"评价: {m.get('evaluation', '-')}")
    lines.append('')

    # ── 金鹰安全 ──
    s = data.get('safety') or {}
    lines.append('【金鹰安全】')
    total_h = s.get('hazard_general', 0) + s.get('hazard_serious', 0) + s.get('hazard_major', 0)
    lines.append(f"隐患: {total_h}条 (一般{s.get('hazard_general', 0)}/严重{s.get('hazard_serious', 0)}/重大{s.get('hazard_major', 0)})")
    if s.get('overdue', 0) > 0:
        lines.append(f"⚠逾期未完成 {s['overdue']}条")
    if s.get('imminent', 0) > 0:
        lines.append(f"⚠即将逾期 {s['imminent']}条")
    if s.get('pending', 0) > 0:
        lines.append(f"未完成 {s['pending']}条")
    if s.get('duty_completed', 0) > 0 or s.get('duty_started', 0) > 0 or s.get('duty_reporting', 0) > 0:
        lines.append(f"履职: 已完成{s.get('duty_completed', 0)}/已开始{s.get('duty_started', 0)}/报备中{s.get('duty_reporting', 0)}")
    if s.get('duty_overdue', 0) > 0:
        lines.append(f"⚠履职已逾期 {s['duty_overdue']}条")
    if s.get('duty_overdue_done', 0) > 0:
        lines.append(f"履职逾期完成 {s['duty_overdue_done']}条")
    if s.get('wp_low', 0) + s.get('wp_high', 0) + s.get('wp_offline', 0) > 0:
        wp_parts = []
        if s.get('wp_low', 0) > 0:
            wp_parts.append(f"失压{s['wp_low']}处")
        if s.get('wp_high', 0) > 0:
            wp_parts.append(f"超压{s['wp_high']}处")
        if s.get('wp_offline', 0) > 0:
            wp_parts.append(f"离线{s['wp_offline']}处")
        lines.append(f"⚠水压异常: {'/'.join(wp_parts)}")
    lines.append('')

    # ── 123设备 ──
    e = data.get('equipment') or {}
    lines.append('【123设备】')
    lines.append(f"总设备: {e.get('total', 0)}台, 故障: {e.get('fault', 0)}台 (故障率{e.get('fault_rate', 0)*100:.1f}%)")
    lines.append('')

    # ── 告警汇总 ──
    has_alert = (m.get('fault', 0) > 0) or \
                (s.get('overdue', 0) > 0 or s.get('imminent', 0) > 0 or
                 s.get('duty_overdue', 0) > 0 or s.get('wp_low', 0) > 0 or s.get('wp_high', 0) > 0) or \
                (e.get('fault', 0) > 0)
    if not has_alert:
        lines.append('各项指标正常，无异常告警')
    else:
        lines.append('⚠ 存在异常项，详见附件故障明细')

    # ── datacenter 链接 ──
    lines.append('')
    lines.append(f'查看完整数据: {_DATACENTER_URL}')

    return '\n'.join(lines)


def _get_project_data(project_name):
    """获取项目三系统数据，确保三个模块都返回(无数据则返回零值)"""
    from calc import calc_meters, calc_safety, calc_equipment

    # ── 瑞信电表 ──
    meters_proj = None
    for p in calc_meters()['projects']:
        if p['project_name'] == project_name:
            meters_proj = p
            break
    if not meters_proj:
        meters_proj = {
            'project_name': project_name, 'total': 0, 'fault': 0,
            'offline': 0, 'abnormal': 0, 'unpaid': 0,
            'fault_rate': 0, 'evaluation': '-',
        }

    # ── 金鹰安全 ──
    safety_proj = None
    for p in calc_safety()['projects']:
        if p['project_name'] == project_name:
            safety_proj = p
            break
    if not safety_proj:
        safety_proj = {
            'project_name': project_name, 'hazard_general': 0, 'hazard_serious': 0,
            'hazard_major': 0, 'overdue': 0, 'imminent': 0, 'pending': 0,
            'duty_completed': 0, 'duty_overdue_done': 0, 'duty_started': 0,
            'duty_overdue': 0, 'duty_reporting': 0,
            'wp_low': 0, 'wp_high': 0, 'wp_offline': 0,
        }

    # ── 123设备 ──
    equip_proj = None
    for p in calc_equipment()['projects']:
        if p['project_name'] == project_name:
            equip_proj = p
            break
    if not equip_proj:
        equip_proj = {
            'project_name': project_name, 'total': 0, 'fault': 0, 'fault_rate': 0,
        }

    return {'meters': meters_proj, 'safety': safety_proj, 'equipment': equip_proj}


# datacenter 访问地址
_DATACENTER_URL = os.environ.get('DATACENTER_URL', 'http://datacenter.zcx-baixiaobai.cn')


def _build_fault_detail_xlsx(project_name, data):
    """生成故障明细xlsx附件(三个sheet: 瑞信电表/金鹰安全/123设备)，返回临时文件路径"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from db import get_conn
    conn = get_conn()

    wb = Workbook()
    # 删默认sheet
    wb.remove(wb.active)

    # 样式
    hdr_font = Font(bold=True, size=11, color='FFFFFF')
    hdr_fill = PatternFill('solid', fgColor='2F5496')
    warn_fill = PatternFill('solid', fgColor='FFF2CC')
    border = Border(*(Side(style='thin', color='D9D9D9'),) * 4)
    hdr_align = Alignment(horizontal='center', vertical='center')
    body_align = Alignment(vertical='center', wrap_text=True)

    def _style_header(ws):
        for cell in ws[1]:
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = hdr_align
            cell.border = border
        ws.freeze_panes = 'A2'

    def _style_body(ws, n_rows):
        for row in ws.iter_rows(min_row=2, max_row=n_rows + 1):
            for cell in row:
                cell.border = border
                cell.alignment = body_align
        # 自动列宽
        for col in ws.columns:
            max_len = max(len(str(c.value or '')) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len * 1.8 + 2, 40)

    has_any = False

    # ════════════════ Sheet 1: 瑞信电表 ════════════════
    m = data.get('meters', {})
    ws1 = wb.create_sheet('瑞信电表')
    m_headers = ['设备ID', '楼栋', '楼层', '房间', '故障类型', '故障描述', '通讯状态', '设备状态', '余额']
    ws1.append(m_headers)
    m_count = 0
    if m.get('total', 0) > 0:
        m_faults = conn.execute("""
            SELECT device_id, building, floor, room, comm_status, device_status,
                   fault_tag, fault_desc, balance
            FROM ruixin_meters
            WHERE project_name=? AND (fault_tag IS NOT NULL AND fault_tag != '')
            ORDER BY fault_tag, device_id
        """, (project_name,)).fetchall()
        for r in m_faults:
            ws1.append([
                r['device_id'] or '', r['building'] or '', r['floor'] or '',
                r['room'] or '', r['fault_tag'] or '', r['fault_desc'] or '',
                r['comm_status'] or '', r['device_status'] or '',
                r['balance'] or '',
            ])
            m_count += 1
    _style_header(ws1)
    _style_body(ws1, m_count)
    if m_count > 0:
        has_any = True

    # ════════════════ Sheet 2: 金鹰安全 ════════════════
    s = data.get('safety', {})
    ws2 = wb.create_sheet('金鹰安全')
    ws2.append(['类别', '子类别', '描述', '责任人', '状态', '剩余天数', '创建时间'])
    s_count = 0
    # 隐患核查(未整改)
    if s.get('hazard_general', 0) + s.get('hazard_serious', 0) + s.get('hazard_major', 0) > 0:
        s_faults = conn.execute("""
            SELECT category, level, responsible, description, hazard_status,
                   remaining_days, create_time
            FROM hazard_inspection
            WHERE project_name=? AND create_days <= 31 AND hazard_status != '已整改'
            ORDER BY level, remaining_days
        """, (project_name,)).fetchall()
        for r in s_faults:
            ws2.append([
                '隐患核查', r['level'] or '', r['description'] or '',
                r['responsible'] or '', r['hazard_status'] or '',
                f"{r['remaining_days']}天" if r['remaining_days'] is not None else '',
                r['create_time'] or '',
            ])
            s_count += 1
    # 履职逾期
    if s.get('duty_overdue', 0) > 0:
        d_faults = conn.execute("""
            SELECT plan_type, plan_content, responsible, plan_status, countdown,
                   start_date, end_date
            FROM safety_duty
            WHERE unit=? AND plan_status='已逾期'
        """, (project_name,)).fetchall()
        for r in d_faults:
            ws2.append([
                '履职逾期', r['plan_type'] or '', r['plan_content'] or '',
                r['responsible'] or '', r['plan_status'] or '',
                f"倒计时{r['countdown']}天" if r['countdown'] is not None else '',
                f"{r['start_date'] or ''}~{r['end_date'] or ''}",
            ])
            s_count += 1
    # 水压异常
    if s.get('wp_low', 0) + s.get('wp_high', 0) > 0:
        w_faults = conn.execute("""
            SELECT device_no, device_name, install_loc, pressure, pressure_fault,
                   report_time, comm_delay, online_status
            FROM water_pressure
            WHERE project_name=? AND (pressure_fault='失压' OR pressure_fault='超压')
        """, (project_name,)).fetchall()
        for r in w_faults:
            ws2.append([
                '水压异常', r['pressure_fault'] or '',
                f"{r['device_name'] or ''} {r['install_loc'] or ''} 压力值{r['pressure'] or ''}",
                r['device_no'] or '', r['online_status'] or '',
                f"时差{r['comm_delay']}天" if r['comm_delay'] is not None else '',
                r['report_time'] or '',
            ])
            s_count += 1
    _style_header(ws2)
    _style_body(ws2, s_count)
    if s_count > 0:
        has_any = True

    # ════════════════ Sheet 3: 123设备 ════════════════
    e = data.get('equipment', {})
    ws3 = wb.create_sheet('123设备')
    ws3.append(['设备ID', '设备名称', '设备类型', '设备分组', '在线状态', '设备状态', '最后通讯', '通讯时差(天)'])
    e_count = 0
    if e.get('fault', 0) > 0:
        e_faults = conn.execute("""
            SELECT device_id, device_name, device_type, device_group, online_status,
                   device_status, last_comm, comm_delay
            FROM equipment_123
            WHERE project_name=? AND comm_delay >= 90
            ORDER BY comm_delay DESC
        """, (project_name,)).fetchall()
        for r in e_faults:
            ws3.append([
                r['device_id'] or '', r['device_name'] or '', r['device_type'] or '',
                r['device_group'] or '', r['online_status'] or '', r['device_status'] or '',
                r['last_comm'] or '', r['comm_delay'] if r['comm_delay'] is not None else '',
            ])
            e_count += 1
    _style_header(ws3)
    _style_body(ws3, e_count)
    if e_count > 0:
        has_any = True

    conn.close()

    if not has_any:
        return None  # 无任何故障明细，不生成附件

    # 写 xlsx 临时文件
    fd, tmp = tempfile.mkstemp(suffix='.xlsx', prefix='fault_detail_', dir=DATA_DIR)
    os.close(fd)  # openpyxl 需要自己打开文件句柄
    wb.save(tmp)
    return tmp


def _email_send_message(to_email, subject, content, attachment=None):
    """通过 agently-cli (QQ邮箱 Agent Mail) 发送邮件
    依赖本机已完成 `agently-cli auth login` 授权。
    attachment: CSV 文件绝对路径(可选), 自动转相对路径传给 --attachment
    返回 (ok: bool, msg: str)，与 _wechat/_feishu_send_message 接口一致。
    """
    import subprocess
    cli = os.environ.get('AGENTLY_CLI', r'C:\Users\Administrator\AppData\Roaming\npm\agently-cli.cmd')
    if not os.path.exists(cli):
        cli = 'agently-cli'  # fallback 到 PATH
    tmp = None
    try:
        # 正文写临时文件(--body-file), 避免命令行长度/特殊字符/引号转义问题
        fd, tmp = tempfile.mkstemp(suffix='.html', prefix='notify_', dir=DATA_DIR)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            # 纯文本换行转 <br>, 邮件正文按 HTML 渲染
            f.write(str(content).replace('\n', '<br>'))
        # agently-cli 要求 --body-file 为相对路径; 设 cwd=DATA_DIR 后只传文件名
        body_rel = os.path.basename(tmp)
        # --confirmed 免两阶段确认(自动化发信); shell=True 让 Windows 能找到 .cmd
        cmd = '"{}" message +send --to "{}" --subject "{}" --body-file "{}"'.format(
            cli, to_email, subject, body_rel)
        # 附件: 相对路径
        if attachment and os.path.exists(attachment):
            att_rel = os.path.basename(attachment)
            cmd += ' --attachment "{}"'.format(att_rel)
        cmd += ' --confirmed'
        r = subprocess.run(cmd, capture_output=True, timeout=120,
                           shell=True, encoding='utf-8', errors='replace',
                           cwd=DATA_DIR)
        if r.returncode == 0:
            return True, '邮件已发送至 {}'.format(to_email)
        err = (r.stderr or r.stdout or '').strip()
        return False, '邮件发送失败(exit {}): {}'.format(r.returncode, err[-500:])
    except FileNotFoundError:
        return False, '未找到 agently-cli，请先 npm install -g @tencent-qqmail/agently-cli'
    except subprocess.TimeoutExpired:
        return False, '邮件发送超时(120s)'
    except Exception as e:
        return False, '邮件发送异常: {}'.format(e)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def send_to_project(project_name):
    """向单个项目发送通知(自动选择渠道)"""
    cfg = _load_config()
    proj_cfg = cfg.get('projects', {}).get(project_name)
    if not proj_cfg or not proj_cfg.get('enabled'):
        return {'error': '该项目未配置通知或已禁用'}

    channel = proj_cfg.get('channel', '')
    target_user = proj_cfg.get('target_user', '')

    data = _get_project_data(project_name)
    if not data:
        return {'error': f'未找到项目数据: {project_name}'}

    content = _build_project_message(project_name, data)

    if channel == 'wechat':
        ok, msg = _wechat_send_message(target_user, content)
    elif channel == 'feishu':
        ok, msg = _feishu_send_message(target_user, content)
    elif channel == 'email':
        subject = '【金鹰数据日报】{}'.format(project_name)
        # 生成故障明细xlsx附件(无故障则返回None)
        xlsx_path = _build_fault_detail_xlsx(project_name, data)
        try:
            ok, msg = _email_send_message(target_user, subject, content, attachment=xlsx_path)
        finally:
            if xlsx_path and os.path.exists(xlsx_path):
                try:
                    os.remove(xlsx_path)
                except Exception:
                    pass
    else:
        return {'error': f'不支持的渠道: {channel}'}

    _add_log(project_name, 'success' if ok else 'error', msg)
    return {'success': ok, 'message': msg} if ok else {'error': msg}


def send_to_all():
    """向所有已配置且启用的项目发送通知"""
    cfg = _load_config()
    projects = cfg.get('projects', {})
    results = []
    for proj_name, pcfg in projects.items():
        if pcfg.get('enabled'):
            try:
                r = send_to_project(proj_name)
                results.append({'project': proj_name, **r})
            except Exception as e:
                _add_log(proj_name, 'error', f'推送异常: {str(e)[:80]}')
                results.append({'project': proj_name, 'error': str(e)[:100]})
            # agently-cli 限制: 10封/分钟, 间隔7秒确保不超限
            time.sleep(7)
    return {'results': results, 'total': len(results)}


def test_send(project_name):
    """测试发送"""
    cfg = _load_config()
    proj_cfg = cfg.get('projects', {}).get(project_name)
    if not proj_cfg:
        return {'error': '该项目未配置通知'}

    channel = proj_cfg.get('channel', '')
    target_user = proj_cfg.get('target_user', '')
    content = f'测试通知\n\n来自金鹰集团数据管理中心\n项目: {project_name}\n渠道: {channel}\n时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'

    if channel == 'wechat':
        ok, msg = _wechat_send_message(target_user, content)
    elif channel == 'feishu':
        ok, msg = _feishu_send_message(target_user, content)
    elif channel == 'email':
        ok, msg = _email_send_message(target_user, '金鹰数据中心测试通知', content)
    else:
        return {'error': f'不支持的渠道: {channel}'}

    _add_log(project_name, 'success' if ok else 'error', f'测试: {msg}')
    return {'success': ok, 'message': msg} if ok else {'error': msg}


# ─── 调度器 ─────────────────────────────────

def scheduler_start():
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return {'message': '调度器已在运行'}
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    _add_log('scheduler', 'info', '通知调度器已启动')
    return {'message': '调度器已启动'}


def scheduler_stop():
    global _scheduler_running
    _scheduler_running = False
    _add_log('scheduler', 'info', '通知调度器已停止')
    return {'message': '调度器已停止'}


def scheduler_is_active():
    return _scheduler_running


def _scheduler_loop():
    global _scheduler_running, _last_send_date
    _scheduler_running = True
    _add_log('scheduler', 'info', '通知调度循环开始')

    # 启动时从文件恢复上次推送日期, 避免重启后重复推送
    try:
        if os.path.exists(SEND_STATE_FILE):
            with open(SEND_STATE_FILE, 'r', encoding='utf-8') as f:
                st = json.load(f) or {}
            _last_send_date = st.get('last_send_date')
            _add_log('scheduler', 'info', f'恢复推送状态: last_send_date={_last_send_date}')
    except Exception as e:
        _add_log('scheduler', 'error', f'恢复推送状态失败: {str(e)[:80]}')

    # 启动补推: 如果今天该推但还没推(enabled 且今天没推过), 启动后立即补推一次
    try:
        cfg0 = _load_config()
        today0 = datetime.now().strftime('%Y-%m-%d')
        if cfg0.get('enabled') and _last_send_date != today0:
            _add_log('scheduler', 'info', '启动补推: 今天尚未推送, 立即执行')
            _last_send_date = today0
            _save_send_state()
            try:
                result = send_to_all()
                ok = sum(1 for x in result['results'] if x.get('success'))
                fail = sum(1 for x in result['results'] if x.get('error'))
                _add_log('scheduler', 'info', f'启动补推完成: {result["total"]}个项目(成功{ok}/失败{fail})')
            except Exception as e:
                _add_log('scheduler', 'error', f'启动补推异常: {str(e)[:80]}')
                _last_send_date = None
                _save_send_state()
    except Exception as e:
        _add_log('scheduler', 'error', f'启动补推检查异常: {str(e)[:80]}')

    while _scheduler_running:
        try:
            cfg = _load_config()
            if not cfg.get('enabled'):
                time.sleep(30)
                continue

            now = datetime.now()
            target_time = cfg.get('daily_time', '09:00').strip()
            current_time = now.strftime('%H:%M')
            today = now.strftime('%Y-%m-%d')

            # 时间窗口匹配: 当前分钟 == 目标时间 且 今天还没推过
            if current_time == target_time and _last_send_date != today:
                _last_send_date = today
                _save_send_state()
                _add_log('scheduler', 'info', f'开始每日推送 ({target_time})')
                try:
                    result = send_to_all()
                    ok = sum(1 for x in result['results'] if x.get('success'))
                    fail = sum(1 for x in result['results'] if x.get('error'))
                    _add_log('scheduler', 'info', f'每日推送完成: {result["total"]}个项目(成功{ok}/失败{fail})')
                except Exception as e:
                    _add_log('scheduler', 'error', f'每日推送异常: {str(e)[:80]}')
                    # 推送异常不重置_last_send_date, 下一轮还能重试
                    _last_send_date = None
                    _save_send_state()

            time.sleep(30)
        except Exception as e:
            _add_log('scheduler', 'error', f'调度异常: {str(e)[:80]}')
            time.sleep(60)
