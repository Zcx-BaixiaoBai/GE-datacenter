"""
金鹰集团数据管理中心 - Flask后端
提供REST API + 托管Vue前端构建产物
启动: python app.py  →  http://localhost:5000
"""
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_conn, init_db, get_table_info
from sync import sync_from_xlsx, get_sync_status
from calc import calc_summary, calc_meters, calc_safety, calc_equipment, calc_budget
import auth
import ai
import sync_controller
import notifier
from functools import wraps

# ─── 路径配置 ──────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIST = os.path.join(PROJECT_DIR, 'frontend', 'dist')
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

# ─── REST API ──────────────────────────────

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})


@app.route('/api/summary')
def api_summary():
    """集团总览KPI"""
    try:
        return jsonify(calc_summary())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/meters')
def api_meters():
    """瑞信电表看板"""
    try:
        data = calc_meters()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/safety')
def api_safety():
    """金鹰安全看板"""
    try:
        return jsonify(calc_safety())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/equipment')
def api_equipment():
    """123设备管理看板"""
    try:
        return jsonify(calc_equipment())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/budget')
def api_budget():
    """预算使用情况"""
    try:
        return jsonify(calc_budget())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/projects')
def api_projects():
    """项目列表(从名称匹配表获取)"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT project_name, pm_name, eng_name, eng_email, erp_code
        FROM name_matching
        WHERE project_name IS NOT NULL AND project_name != ''
        ORDER BY project_name
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/sync/status')
def api_sync_status():
    """同步状态"""
    return jsonify(get_sync_status())


@app.route('/api/sync', methods=['POST'])
def api_sync():
    """触发数据同步(上传xlsx文件)"""
    if 'file' not in request.files:
        # 尝试用默认文件同步
        default_xlsx = os.path.join(DATA_DIR, '总控表_集控表.xlsx')
        if os.path.exists(default_xlsx):
            result = sync_from_xlsx(default_xlsx, do_reset=True)
            return jsonify(result)
        return jsonify({'error': 'No file uploaded and no default xlsx found'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    if not filename.endswith(('.xlsx', '.xlsm')):
        return jsonify({'error': 'Only .xlsx/.xlsm files are supported'}), 400

    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    result = sync_from_xlsx(filepath, do_reset=True)
    return jsonify(result)


@app.route('/api/db/tables')
def api_db_tables():
    """数据库表信息"""
    return jsonify(get_table_info())


@app.route('/api/meters/detail')
def api_meters_detail():
    """瑞信电表明细(故障表具列表)"""
    conn = get_conn()
    project = request.args.get('project', '')
    fault_only = request.args.get('fault_only', '0') == '1'

    query = """
        SELECT project_name, building, room, install_addr, location,
               switch_status, fault_tag, fault_desc, data_time, offline_hours
        FROM ruixin_meters
        WHERE project_name IS NOT NULL AND project_name != ''
    """
    params = []
    if project:
        query += " AND project_name = ?"
        params.append(project)
    if fault_only:
        query += " AND (fault_tag IS NOT NULL AND fault_tag != '')"
    query += " ORDER BY project_name, fault_tag DESC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/equipment/detail')
def api_equipment_detail():
    """123设备明细"""
    conn = get_conn()
    project = request.args.get('project', '')
    fault_only = request.args.get('fault_only', '0') == '1'

    query = """
        SELECT project_name, device_name, device_type, online_status,
               device_status, last_comm, comm_delay, firmware
        FROM equipment_123
        WHERE project_name IS NOT NULL AND project_name != ''
    """
    params = []
    if project:
        query += " AND project_name = ?"
        params.append(project)
    if fault_only:
        query += " AND comm_delay >= 90"
    query += " ORDER BY project_name, comm_delay DESC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/safety/hazards')
def api_safety_hazards():
    """隐患核查明细"""
    conn = get_conn()
    project = request.args.get('project', '')
    status = request.args.get('status', '')

    query = """
        SELECT project_name, category, level, responsible, deadline,
               description, hazard_status, remaining_days, create_time
        FROM hazard_inspection
        WHERE project_name IS NOT NULL AND project_name != ''
    """
    params = []
    if project:
        query += " AND project_name = ?"
        params.append(project)
    if status:
        query += " AND hazard_status = ?"
        params.append(status)
    query += " ORDER BY remaining_days ASC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/safety/duties')
def api_safety_duties():
    """安全履职明细"""
    conn = get_conn()
    project = request.args.get('project', '')
    status = request.args.get('status', '')

    query = """
        SELECT unit, plan_type, start_date, end_date, plan_status,
               responsible, position, countdown
        FROM safety_duty
        WHERE unit IS NOT NULL AND unit != ''
    """
    params = []
    if project:
        query += " AND unit = ?"
        params.append(project)
    if status:
        query += " AND plan_status = ?"
        params.append(status)
    query += " ORDER BY countdown ASC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ═══════════════════════════════════════════════════════
#  管理员认证
# ═══════════════════════════════════════════════════════

def require_admin(f):
    """管理员认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '')
        project = auth.check_token(token)
        if not project:
            return jsonify({'error': '需要登录', 'auth_required': True}), 401
        if project != 'admin':
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated


def require_login(f):
    """登录认证装饰器(管理员+项目用户均可)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token', '')
        project = auth.check_token(token)
        if not project:
            return jsonify({'error': '需要登录', 'auth_required': True}), 401
        request.current_project = project  # 'admin' 或项目名
        request.is_admin = (project == 'admin')
        return f(*args, **kwargs)
    return decorated


def _get_project_filter():
    """获取当前用户的项目过滤(管理员返回None=不过滤)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    project = auth.get_project_from_token(token)
    if project == 'admin' or not project:
        return None  # 管理员不过滤
    return project  # 项目用户只看自己的


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    password = request.json.get('password', '')
    project = request.json.get('project', 'admin')
    result = auth.login(password, project)
    if result:
        return jsonify(result)
    return jsonify({'error': '密码错误'}), 401


@app.route('/api/auth/check')
def api_auth_check():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    project = auth.check_token(token)
    return jsonify({
        'authenticated': bool(project),
        'project': project,
        'is_admin': project == 'admin',
        'is_default': auth.is_default_password()
    })


@app.route('/api/auth/projects')
def api_auth_projects():
    """获取可选项目列表(登录页用)"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT project_name FROM name_matching
        WHERE project_name IS NOT NULL AND project_name != ''
        ORDER BY project_name
    """).fetchall()
    conn.close()
    projects = [r['project_name'] for r in rows]
    # 合并已配置密码的项目
    configured = auth.get_project_list()
    return jsonify({'projects': projects, 'configured': configured})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    auth.logout(token)
    return jsonify({'message': '已登出'})


@app.route('/api/auth/change-password', methods=['POST'])
@require_admin
def api_change_password():
    old = request.json.get('old_password', '')
    new = request.json.get('new_password', '')
    ok, msg = auth.change_password(old, new)
    return jsonify({'success': ok, 'message': msg})


# ═══════════════════════════════════════════════════════
#  数据同步模块 (集控中心, 管理员权限)
# ═══════════════════════════════════════════════════════

@app.route('/api/sync-center/status')
@require_admin
def api_sync_center_status():
    return jsonify({'modules': sync_controller.get_status(), 'scheduler_active': sync_controller.scheduler_is_active()})


@app.route('/api/sync-center/trigger', methods=['POST'])
@require_admin
def api_sync_center_trigger():
    mid = request.json.get('module', '')
    return jsonify(sync_controller.trigger_sync(mid))


@app.route('/api/sync-center/trigger-all', methods=['POST'])
@require_admin
def api_sync_center_trigger_all():
    return jsonify(sync_controller.trigger_all_sync())


@app.route('/api/sync-center/scheduler/start', methods=['POST'])
@require_admin
def api_sync_center_scheduler_start():
    return jsonify(sync_controller.scheduler_start())


@app.route('/api/sync-center/scheduler/stop', methods=['POST'])
@require_admin
def api_sync_center_scheduler_stop():
    return jsonify(sync_controller.scheduler_stop())


@app.route('/api/sync-center/config', methods=['GET', 'POST'])
@require_admin
def api_sync_center_config():
    if request.method == 'POST':
        return jsonify(sync_controller.update_sync_config(request.json))
    return jsonify(sync_controller._load_sync_config())


@app.route('/api/sync-center/logs')
@require_admin
def api_sync_center_logs():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(sync_controller.get_logs(limit))


# ═══════════════════════════════════════════════════════
#  AI 沟通模块
# ═══════════════════════════════════════════════════════

@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    msg = request.json.get('message', '')
    history = request.json.get('history', [])
    user_id = request.json.get('user_id', 'web_user')
    # 判定管理员身份: 写库工具仅对管理员开放
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    is_admin = auth.is_admin(token)
    if not msg:
        return jsonify({'error': '请输入消息'}), 400
    result = ai.chat(msg, history, user_id=user_id, is_admin=is_admin)
    return jsonify(result)


@app.route('/api/ai/config', methods=['GET', 'POST'])
@require_admin
def api_ai_config():
    if request.method == 'POST':
        return jsonify(ai.update_config(request.json))
    cfg = ai.load_config()
    # 隐藏完整key
    key = cfg.get('api_key', '')
    cfg['api_key_masked'] = key[:8] + '****' + key[-4:] if len(key) > 12 else '****'
    cfg['api_key'] = ''  # 不返回完整key
    return jsonify(cfg)


@app.route('/api/ai/test', methods=['POST'])
@require_admin
def api_ai_test():
    return jsonify(ai.test_connection())


@app.route('/api/ai/data-context')
@require_admin
def api_ai_data_context():
    """预览AI数据上下文"""
    return jsonify({'context': ai.build_data_context()})


# ═══════════════════════════════════════════════════════
#  通知推送模块 (飞书OpenAPI + 微信iLink Bot)
# ═══════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════
#  通知推送模块 (登录用户可访问, 管理员看全部, 项目用户看自己的)
# ═══════════════════════════════════════════════════════

@app.route('/api/notify/config', methods=['GET', 'POST'])
@require_login
def api_notify_config():
    proj = _get_project_filter()
    if request.method == 'POST':
        if not request.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return jsonify(notifier.update_config(request.json))
    cfg = notifier.get_config()
    if proj:  # 项目用户只看自己的
        cfg['projects'] = {k: v for k, v in cfg.get('projects', {}).items() if k == proj}
    return jsonify(cfg)

@app.route('/api/notify/project', methods=['POST', 'DELETE'])
@require_login
def api_notify_project():
    if request.method == 'POST':
        d = request.json
        project = d.get('project_name', '')
        if not request.is_admin and project != request.current_project:
            return jsonify({'error': '只能操作本项目'}), 403
        return jsonify(notifier.set_project_config(
            project, d.get('channel'), d.get('target_user'), d.get('target_session'), d.get('enabled', True)
        ))
    elif request.method == 'DELETE':
        project = request.args.get('project', '')
        if not request.is_admin and project != request.current_project:
            return jsonify({'error': '只能操作本项目'}), 403
        notifier.delete_project_config(project)
        return jsonify({'message': '已删除'})

@app.route('/api/notify/test', methods=['POST'])
@require_login
def api_notify_test():
    project = request.json.get('project_name', '')
    if not request.is_admin and project != request.current_project:
        return jsonify({'error': '只能测试本项目'}), 403
    return jsonify(notifier.test_send(project))

@app.route('/api/notify/user', methods=['DELETE'])
@require_login
def api_notify_remove_user():
    """删除已绑定用户"""
    if not request.is_admin:
        return jsonify({'error': '需要管理员权限'}), 403
    uid = request.args.get('uid', '')
    if not uid:
        return jsonify({'error': '缺少用户ID'}), 400
    users = notifier._load_wechat_users()
    if uid in users:
        del users[uid]
        notifier._save_wechat_users(users)
        return jsonify({'message': '已删除用户'})
    return jsonify({'error': '用户不存在'}), 404

@app.route('/api/notify/trigger', methods=['POST'])
@require_admin
def api_notify_trigger():
    return jsonify(notifier.send_to_all())

@app.route('/api/notify/logs')
@require_login
def api_notify_logs():
    limit = request.args.get('limit', 50, type=int)
    proj = _get_project_filter()
    logs = notifier.get_logs(limit)
    if proj:  # 项目用户只看自己项目的日志
        logs = [l for l in logs if l.get('project') == proj or l.get('project') == 'scheduler']
    return jsonify(logs)

@app.route('/api/notify/scheduler/start', methods=['POST'])
@require_admin
def api_notify_scheduler_start():
    return jsonify(notifier.scheduler_start())

@app.route('/api/notify/scheduler/stop', methods=['POST'])
@require_admin
def api_notify_scheduler_stop():
    return jsonify(notifier.scheduler_stop())

@app.route('/api/notify/status')
@require_login
def api_notify_status():
    cfg = notifier._load_config()
    return jsonify({
        'enabled': cfg.get('enabled', False),
        'daily_time': cfg.get('daily_time', '09:00'),
        'scheduler_active': notifier.scheduler_is_active(),
        'project_count': len(cfg.get('projects', {})),
    })

# ─── 项目密码管理 (管理员) ──────────────────

@app.route('/api/notify/project-password', methods=['POST'])
@require_admin
def api_notify_project_password():
    d = request.json
    auth.set_project_password(d.get('project', ''), d.get('password', ''))
    return jsonify({'message': '密码已设置'})

# ─── 独立通知推送 (不依赖 QwenPaw) ──────────────

@app.route('/api/notify/qrcode/<channel>')
@require_login
def api_notify_qrcode(channel):
    """获取微信/飞书扫码二维码 (独立调用, 不走 QwenPaw)"""
    if channel == 'wechat':
        return jsonify(notifier.wechat_get_qrcode())
    elif channel == 'feishu':
        return jsonify(notifier.feishu_get_qrcode())
    return jsonify({'error': '不支持的渠道'}), 400

@app.route('/api/notify/qrcode/<channel>/status')
@require_login
def api_notify_qrcode_status(channel):
    """轮询扫码状态"""
    token = request.args.get('token', '')
    if channel == 'wechat':
        return jsonify(notifier.wechat_poll_status(token))
    elif channel == 'feishu':
        return jsonify(notifier.feishu_poll_status(token))
    return jsonify({'error': '不支持的渠道'}), 400

@app.route('/api/notify/wechat/status')
@require_login
def api_notify_wechat_status():
    """获取微信登录状态、轮询状态和已激活用户"""
    info = notifier.wechat_get_user_info()
    info['poller_active'] = notifier._wechat_poller_running
    return jsonify(info)

@app.route('/api/notify/wechat/poller/start', methods=['POST'])
@require_login
def api_notify_wechat_poller_start():
    """手动启动微信消息轮询"""
    return jsonify({'message': notifier._start_wechat_poller()})

@app.route('/api/notify/wechat/poller/stop', methods=['POST'])
@require_login
def api_notify_wechat_poller_stop():
    """停止微信消息轮询"""
    notifier._stop_wechat_poller()
    return jsonify({'message': '微信轮询已停止'})

@app.route('/api/notify/feishu/status')
@require_login
def api_notify_feishu_status():
    """获取飞书绑定状态"""
    return jsonify(notifier.feishu_get_status())

@app.route('/api/notify/feishu/webhook', methods=['POST'])
def api_notify_feishu_webhook():
    """飞书 webhook 备用入口 (WebSocket 优先)"""
    event_data = request.json
    result = notifier.feishu_handle_webhook(event_data)
    return jsonify(result)

@app.route('/api/notify/feishu/ws/start', methods=['POST'])
@require_login
def api_notify_feishu_ws_start():
    """启动飞书 WebSocket 长连接"""
    return jsonify({'message': notifier._start_feishu_ws()})

@app.route('/api/notify/feishu/ws/stop', methods=['POST'])
@require_login
def api_notify_feishu_ws_stop():
    """停止飞书 WebSocket"""
    notifier._stop_feishu_ws()
    return jsonify({'message': '飞书WebSocket已停止'})

@app.route('/api/notify/feishu/test', methods=['POST'])
@require_login
def api_notify_feishu_test():
    """测试飞书推送(给自己发一条测试消息)"""
    token = notifier._get_feishu_token()
    if not token:
        return jsonify({'ok': False, 'msg': '飞书未绑定或token获取失败'})
    ok, msg = notifier._feishu_send_message('self', f'测试通知\n\n来自金鹰集团数据管理中心\n时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    return jsonify({'ok': ok, 'msg': msg})


# ─── 静态文件托管(Vue前端) ──────────────────

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIST, 'index.html')


@app.route('/<path:path>')
def static_proxy(path):
    """托管Vue前端的静态资源"""
    file_path = os.path.join(FRONTEND_DIST, path)
    if os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIST, path)
    # Vue Router history mode: 非API路由返回index.html
    return send_from_directory(FRONTEND_DIST, 'index.html')


# ─── 启动 ──────────────────────────────────

def ensure_data():
    """确保数据库已初始化且有数据"""
    init_db()
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM sync_log").fetchone()[0]
    conn.close()
    if count == 0:
        default_xlsx = os.path.join(DATA_DIR, '总控表_集控表.xlsx')
        if os.path.exists(default_xlsx):
            print(f"[自动同步] 检测到默认xlsx, 开始同步...")
            sync_from_xlsx(default_xlsx, do_reset=True)

    # 自动启动微信和飞书的长连接 (单独try, 失败不影响调度器)
    try:
        import notifier
        # 微信: 如果已登录, 启动消息轮询
        token = notifier._load_wechat_token()
        if token.get('bot_token'):
            print("[自动启动] 微信消息轮询...")
            notifier._start_wechat_poller()
        # 飞书: 如果已绑定, 启动 WebSocket
        creds = notifier._load_feishu_creds()
        if creds.get('app_id'):
            print("[自动启动] 飞书WebSocket...")
            notifier._start_feishu_ws()
    except Exception as e:
        print(f"[启动] 长连接启动失败: {e}")

    # 通知调度器: 若配置已启用, 自动恢复定时推送 (独立try, 不受长连接影响)
    try:
        import notifier
        notify_cfg = notifier._load_config()
        if notify_cfg.get('enabled'):
            print("[自动启动] 通知调度器...")
            notifier.scheduler_start()
    except Exception as e:
        print(f"[启动] 通知调度器启动失败: {e}")

    # 数据同步调度器: 若有模块设了间隔, 自动恢复定时同步 (独立try)
    try:
        import sync_controller
        sync_cfg = sync_controller._load_sync_config()
        has_interval = any(sync_cfg.get(f'{mid}_interval_min', 0) > 0 for mid in sync_controller.MODULES)
        if has_interval:
            print("[自动启动] 数据同步调度器...")
            sync_controller.scheduler_start()
    except Exception as e:
        print(f"[启动] 数据同步调度器启动失败: {e}")


if __name__ == '__main__':
    ensure_data()
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  金鹰集团数据管理中心")
    print(f"  服务地址: http://localhost:{port}")
    print(f"  API文档: http://localhost:{port}/api/health")
    print(f"  前端目录: {FRONTEND_DIST}")
    print()
    # debug=False: 关闭reloader, 避免后台线程(微信轮询/飞书WS/调度器)
    # 与服务进程内存隔离导致推送失效; threaded=True避免后台同步请求阻塞
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
