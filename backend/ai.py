"""
金鹰集团数据管理中心 - AI沟通模块
自动注入当前业务数据作为上下文, 调用配置的LLM API
管理员可配置: URL / API Key / Model / System Prompt / Temperature
支持: 1)全量汇总数据注入  2)按需查数据库(通过SQL查询)
"""
import os
import json
import requests
import sqlite3

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ai_config.json')
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'center.db')

DEFAULT_CONFIG = {
    "api_url": "https://api.openai.com/v1/chat/completions",
    "api_key": "",
    "model": "gpt-4o",
    "system_prompt": "你是金鹰集团数据管理中心的AI助手。你可以查看和分析电表、安全、设备、预算等全部数据。请基于提供的数据准确回答问题。如果汇总数据中没有具体明细，可以使用查询工具查数据库获取明细。回答时请引用具体数据。",
    "temperature": 0.3,
    "max_tokens": 4096,
}


def _normalize_url(url):
    """自动补全API URL"""
    url = url.rstrip('/')
    if url.endswith('/chat/completions'):
        return url
    if 'maas.aliyuncs.com' in url and url.endswith('/api/v1'):
        return url.replace('/api/v1', '/compatible-mode/v1/chat/completions')
    if url.endswith('/v1'):
        return url + '/chat/completions'
    return url + '/chat/completions'


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except:
            pass
    _save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def _save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_config(new_cfg):
    cfg = load_config()
    for key in ['api_url', 'api_key', 'model', 'system_prompt', 'temperature', 'max_tokens']:
        if key in new_cfg:
            cfg[key] = new_cfg[key]
    _save_config(cfg)
    return cfg


# ─── 数据上下文: 全量汇总数据 ─────────────────────────────────

def build_data_context(is_admin=False):
    """构建完整数据上下文 - 包含所有项目的汇总数据"""
    from calc import calc_summary, calc_meters, calc_safety, calc_equipment, calc_budget

    ctx = "=== 当前数据快照(全量) ===\n\n"

    # 集团总览
    try:
        s = calc_summary()
        ctx += "【集团总览】\n"
        ctx += f"- 智能电表: 共{s['meters']['total']}块, 故障{s['meters']['fault']}块, "
        ctx += f"离线{s['meters']['offline']}, 异常送电{s['meters']['abnormal']}, 无签呈后付费{s['meters']['unpaid']}, "
        ctx += f"故障率{s['meters']['fault_rate']*100:.2f}%, 覆盖{s['meters']['project_count']}个项目\n"
        ctx += f"- 安全: 隐患总数{s['safety']['hazard_total']}, 逾期{s['safety']['hazard_overdue']}, "
        ctx += f"即将逾期{s['safety']['hazard_imminent']}, 安全履职{s['safety']['duty_total']}条, "
        ctx += f"已逾期{s['safety']['duty_overdue']}, 水压失压{s['safety']['wp_low']}, "
        ctx += f"覆盖{s['safety']['project_count']}个项目\n"
        ctx += f"- 123设备: 总设备{s['equipment']['total']}台, 故障{s['equipment']['fault']}台, "
        ctx += f"故障率{s['equipment']['fault_rate']*100:.1f}%, 覆盖{s['equipment']['project_count']}个项目\n"
    except Exception as e:
        ctx += f"(总览数据获取失败: {e})\n"

    # 瑞信电表 - 全部项目(不只TOP10)
    try:
        m = calc_meters()
        ctx += "\n【瑞信电表-全部项目明细】\n"
        for p in m['projects']:
            ctx += f"  {p['rank']}. {p['project_name']}: 总{p['total']}块, 故障{p['fault']}, "
            ctx += f"离线{p['offline']}, 异常送电{p['abnormal']}, 无签呈{p['unpaid']}, "
            ctx += f"故障率{p['fault_rate']*100:.2f}%, 评价[{p['evaluation']}], "
            ctx += f"负责人{p['pm_name']}, 工程负责人{p['eng_name']}\n"
    except Exception as e:
        ctx += f"(电表数据获取失败: {e})\n"

    # 金鹰安全 - 全部项目
    try:
        sf = calc_safety()
        ctx += "\n【金鹰安全-全部项目明细】\n"
        for p in sf['projects']:
            total_h = p['hazard_general'] + p['hazard_serious'] + p['hazard_major']
            ctx += f"  {p['project_name']}: 隐患{total_h}(一般{p['hazard_general']}/严重{p['hazard_serious']}/重大{p['hazard_major']}), "
            ctx += f"逾期{p['overdue']}, 即将逾期{p['imminent']}, "
            ctx += f"履职完成{p['duty_completed']}, 已逾期{p['duty_overdue']}, "
            ctx += f"水压失压{p['wp_low']}, 离线{p['wp_offline']}\n"
    except Exception as e:
        ctx += f"(安全数据获取失败: {e})\n"

    # 123设备 - 全部项目
    try:
        eq = calc_equipment()
        ctx += "\n【123设备-全部项目明细】\n"
        for p in eq['projects']:
            ctx += f"  {p['project_name']}: 总{p['total']}台, 故障{p['fault']}台, 故障率{p['fault_rate']*100:.1f}%\n"
    except Exception as e:
        ctx += f"(设备数据获取失败: {e})\n"

    # 预算汇总
    try:
        bd = calc_budget()
        s = bd.get('summary', {})
        if s and s.get('categories'):
            ctx += "\n【预算使用-集团汇总】\n"
            for cat, vals in list(s['categories'].items())[:8]:
                ctx += f"  {cat}: 当期{vals.get('current_usage',0)}, "
                ctx += f"当年{vals.get('yearly_usage',0)}, 占比{vals.get('yearly_rate','0')}\n"
    except Exception as e:
        ctx += f"(预算数据获取失败: {e})\n"

    ctx += "\n=== 数据快照结束 ===\n"
    ctx += "\n注意: 以上是各项目汇总数据。如需查看具体明细(如某项目的故障电表列表、隐患清单等), "
    ctx += "请在回复中使用 [QUERY]SQL语句[/QUERY] 标记, 系统会自动执行查询并补充结果。"
    ctx += "\n可用表及关键字段:"
    ctx += "\n- ruixin_meters: 电表明细. 关键字段: project_name(项目名), building(楼栋), room(房间), "
    ctx += "install_addr(仪表号), switch_status(开关状态), fault_tag(故障类型,值为【离线】/【异常送电】/【无签呈后付费】), "
    ctx += "fault_desc(故障描述), device_status(设备状态:在线), comm_status(通讯状态), data_time(数据时间), balance(余额)"
    ctx += "\n  查故障电表: SELECT project_name, install_addr, room, fault_tag, fault_desc FROM ruixin_meters "
    ctx += "WHERE project_name = '项目名' AND fault_tag != '' AND fault_tag IS NOT NULL"
    ctx += "\n  ⚠ 重要: fault_tag的值带【】括号(如【无签呈后付费】、【离线】、【异常送电】), "
    ctx += "查询时务必用 LIKE '%关键字%' 而非精确匹配, 否则返回0行"
    ctx += "\n- equipment_123: 设备明细. 关键字段: project_name, device_name, online_status, device_status, comm_delay(通讯时差), last_comm"
    ctx += "\n  查故障设备: SELECT project_name, device_name, last_comm, comm_delay FROM equipment_123 "
    ctx += "WHERE project_name = '项目名' AND comm_delay >= 90"
    ctx += "\n- hazard_inspection: 隐患明细. 关键字段: project_name, category, level, description, hazard_status, remaining_days, responsible"
    ctx += "\n- safety_duty: 安全履职. 关键字段: unit(项目名), plan_type, plan_status, responsible, countdown"
    ctx += "\n- water_pressure: 末端水压. 关键字段: project_name, pressure, pressure_fault, report_time"
    ctx += "\n- commerce_budget/property_budget: 预算. 关键字段: subject, period, unit, actual_cost, adjusted_budget"
    ctx += "\n- name_matching: 项目匹配. 关键字段: project_name, pm_name, eng_name, erp_code"

    # ─── 管理员专属: 登记写库工具 (仅管理员可见) ───
    if is_admin:
        ctx += "\n\n=== 登记写库工具(仅管理员可用) ==="
        ctx += "\n你拥有向两张登记表追加记录的能力, 用于处理故障登记/后付费登记。"
        ctx += "\n注意: 这两个工具只能【新增】记录, 不能修改或删除。"
        ctx += "\n\n1) 故障登记: 把一块电表登记为【已报备故障】。登记后该电表将被视为已报备, "
        ctx += "其【离线】/【异常送电】/【无签呈后付费】等故障标记会被消除。"
        ctx += "\n   适用场景: 某块故障电表已经在线下报备处理, 需要从故障统计中消除。"
        ctx += "\n   用法: 在回复中写 [REGISTER_FAULT]{\"project_name\":\"项目名\",\"meter_no\":\"仪表号\"}[/REGISTER_FAULT]"
        ctx += "\n   必填: project_name(项目名), meter_no(仪表号, 对应ruixin_meters.install_addr)"
        ctx += "\n   选填: room_name(房间名), meter_name(仪表名称), identity(所属身份), meter_type(仪表类型)"
        ctx += "\n   系统会自动校验重复登记, 成功后重算故障状态。"
        ctx += "\n\n2) 后付费登记: 把一个房间登记为【后付费】, 登记后该房间的电表不再判异常送电/无签呈后付费。"
        ctx += "\n   适用场景: 某房间已办理后付费签呈, 需要从异常送电统计中消除。"
        ctx += "\n   用法: 在回复中写 [REGISTER_POSTPAID]{\"room_id\":\"房间id\"}[/REGISTER_POSTPAID]"
        ctx += "\n   必填: room_id(房间id, 对应ruixin_meters.room_id)"
        ctx += "\n   选填: meter_name(仪表名称), meter_no(表号), remark(备注), identity(所属身份), project_name(项目名)"
        ctx += "\n   系统会自动校验重复登记, 成功后重算故障状态。"
        ctx += "\n\n重要: 执行登记前, 建议先用 [QUERY] 查一下该电表当前是否确实是故障状态, "
        ctx += "确认后再登记。登记操作会真实写入数据库, 请务必确认信息准确。"
    return ctx


# ─── SQL 查询工具 ─────────────────────────────────

def _execute_sql(sql):
    """执行只读SQL查询, 返回结果"""
    # 安全检查: 只允许SELECT
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith('SELECT'):
        return {'error': '只允许SELECT查询'}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        # 格式化为文本表格
        result = f'查询结果 ({len(rows)}行):\n'
        result += ' | '.join(columns) + '\n'
        result += '-' * 80 + '\n'
        for row in rows[:50]:  # 最多50行
            result += ' | '.join(str(row[c] or '') for c in columns) + '\n'
        if len(rows) > 50:
            result += f'... 还有 {len(rows)-50} 行\n'
        return result
    except Exception as e:
        return f'查询失败: {str(e)}'


def _extract_and_run_queries(text):
    """从AI回复中提取 [QUERY]...[/QUERY] 标记, 执行SQL, 补充结果"""
    import re
    queries = re.findall(r'\[QUERY\](.*?)\[/QUERY\]', text, re.DOTALL)
    if not queries:
        return []

    results = []
    for i, sql in enumerate(queries):
        sql = sql.strip()
        result = _execute_sql(sql)
        results.append(f'\n--- 查询{i+1}结果 ---\nSQL: {sql[:100]}\n{result}\n')

    return results


# ─── 写库工具: 仅允许 INSERT 到两张登记表 ─────────────────────────────────
# 安全约束: 不暴露表名/SQL给LLM拼装, 字段走白名单, 全参数化(?占位符),
#          代码层禁止任何UPDATE/DELETE, 写后重算公式列, 全程记审计日志

from datetime import datetime as _dt


def _parse_tool_params(block):
    """解析工具标记内容为dict. 兼容JSON与 key:value 多行格式"""
    block = block.strip()
    import json
    try:
        return json.loads(block)
    except Exception:
        pass
    # 容错: key: value / key = value 多行
    params = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            k, v = line.split(':', 1)
        elif '=' in line:
            k, v = line.split('=', 1)
        else:
            continue
        params[k.strip()] = v.strip().strip('"').strip("'")
    return params


# reported_faults 可写字段白名单 (必填: project_name, meter_no)
# 注: meter_no 对应 ruixin_meters.install_addr(仪表号)
_FAULT_FIELDS = ['room_name', 'meter_name', 'meter_no', 'identity',
                 'meter_type', 'project_name']

# postpaid_register 可写字段白名单 (必填: room_id)
_POSTPAID_FIELDS = ['meter_name', 'meter_no', 'room_id', 'remark',
                    'identity', 'project_name']


def _log_ai_write(operator, action, table_name, payload, result):
    """写审计日志到 ai_write_log"""
    try:
        import json
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO ai_write_log (operator, action, table_name, payload, result, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (operator, action, table_name,
             json.dumps(payload, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False),
             _dt.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ai_write_log] 审计日志写入失败: {e}")


def _execute_register_fault(params, operator='admin'):
    """登记已报备故障: 往 reported_faults 追加一条记录.
    必填: project_name, meter_no. 追加后该电表的故障标记会被消除(sync时is_reported跳过判定)."""
    project_name = (str(params.get('project_name') or '')).strip()
    meter_no = (str(params.get('meter_no') or '')).strip()
    if not project_name or not meter_no:
        return {'error': '登记故障需提供 project_name 和 meter_no', 'params': params}

    # 白名单过滤, 只允许写登记语义字段
    fields = [f for f in _FAULT_FIELDS if params.get(f) not in (None, '')]
    for req in ('project_name', 'meter_no'):
        if req not in fields:
            fields.append(req)
    values = [str(params.get(f)).strip() for f in fields]

    try:
        conn = sqlite3.connect(DB_PATH)
        # 重复登记校验
        existing = conn.execute(
            "SELECT id FROM reported_faults WHERE project_name=? AND meter_no=?",
            (project_name, meter_no)
        ).fetchone()
        if existing:
            conn.close()
            result = {'error': '该电表已登记报备, 无需重复登记',
                       'project_name': project_name, 'meter_no': meter_no,
                       'existing_id': existing[0]}
            _log_ai_write(operator, 'register_fault', 'reported_faults', params, result)
            return result

        placeholders = ','.join('?' * len(fields))
        col_list = ','.join(fields)
        cursor = conn.execute(
            f"INSERT INTO reported_faults ({col_list}) VALUES ({placeholders})",
            values
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        result = {'ok': True, 'id': new_id, 'table': 'reported_faults',
                  'project_name': project_name, 'meter_no': meter_no,
                  'fields': fields}
        _log_ai_write(operator, 'register_fault', 'reported_faults', params, result)
        return result
    except Exception as e:
        result = {'error': f'登记失败: {e}', 'params': params}
        _log_ai_write(operator, 'register_fault', 'reported_faults', params, result)
        return result


def _execute_register_postpaid(params, operator='admin'):
    """登记后付费: 往 postpaid_register 追加一条记录.
    必填: room_id. 追加后该房间的电表不再判异常送电/无签呈后付费."""
    room_id = (str(params.get('room_id') or '')).strip()
    if not room_id:
        return {'error': '登记后付费需提供 room_id', 'params': params}

    fields = [f for f in _POSTPAID_FIELDS if params.get(f) not in (None, '')]
    if 'room_id' not in fields:
        fields.append('room_id')
    values = [str(params.get(f)).strip() for f in fields]

    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute(
            "SELECT id FROM postpaid_register WHERE room_id=?",
            (room_id,)
        ).fetchone()
        if existing:
            conn.close()
            result = {'error': '该房间已登记后付费, 无需重复登记',
                       'room_id': room_id, 'existing_id': existing[0]}
            _log_ai_write(operator, 'register_postpaid', 'postpaid_register', params, result)
            return result

        placeholders = ','.join('?' * len(fields))
        col_list = ','.join(fields)
        cursor = conn.execute(
            f"INSERT INTO postpaid_register ({col_list}) VALUES ({placeholders})",
            values
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        result = {'ok': True, 'id': new_id, 'table': 'postpaid_register',
                  'room_id': room_id, 'fields': fields}
        _log_ai_write(operator, 'register_postpaid', 'postpaid_register', params, result)
        return result
    except Exception as e:
        result = {'error': f'登记失败: {e}', 'params': params}
        _log_ai_write(operator, 'register_postpaid', 'postpaid_register', params, result)
        return result


def _recalc_formula_columns():
    """写库后重算公式列, 让故障状态立即刷新. 复用sync逻辑, 全量重算(登记低频可接受)."""
    try:
        from sync import compute_formula_columns
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # sync逻辑用字段名访问, 必须设Row
        compute_formula_columns(conn)
        conn.commit()
        conn.close()
        return {'ok': True, 'msg': '公式列已重算, 故障状态已刷新'}
    except Exception as e:
        return {'error': f'重算失败(数据已写入, 故障状态将在下次同步时刷新): {e}'}


def _extract_and_run_registers(text, operator='admin'):
    """从AI回复中提取 [REGISTER_FAULT]...[/REGISTER_FAULT] 和
    [REGISTER_POSTPAID]...[/REGISTER_POSTPAID] 标记, 执行登记写库, 补充结果"""
    import re
    fault_blocks = re.findall(r'\[REGISTER_FAULT\](.*?)\[/REGISTER_FAULT\]', text, re.DOTALL)
    postpaid_blocks = re.findall(r'\[REGISTER_POSTPAID\](.*?)\[/REGISTER_POSTPAID\]', text, re.DOTALL)

    if not fault_blocks and not postpaid_blocks:
        return []

    results = []
    need_recalc = False
    for i, block in enumerate(fault_blocks):
        params = _parse_tool_params(block)
        r = _execute_register_fault(params, operator=operator)
        results.append(f'\n--- 故障登记{i+1} ---\n参数: {params}\n结果: {r}\n')
        need_recalc = True

    for i, block in enumerate(postpaid_blocks):
        params = _parse_tool_params(block)
        r = _execute_register_postpaid(params, operator=operator)
        results.append(f'\n--- 后付费登记{i+1} ---\n参数: {params}\n结果: {r}\n')
        need_recalc = True

    # 所有登记完成后统一重算一次公式列
    if need_recalc:
        recalc = _recalc_formula_columns()
        results.append(f'\n--- 故障状态重算 ---\n{recalc}\n')

    return results



# ─── 会话记忆: 每个用户独立对话历史 ─────────────────────────────────

import time as _time

# 内存中的会话历史: {user_id: [{"role": "user"/"assistant", "content": "...", "time": ts}]}
_session_histories = {}
_SESSION_MAX_TURNS = 20      # 每个会话最多保留20轮(40条消息)
_SESSION_TTL = 3600         # 会话1小时不活动自动清理


def get_session_history(user_id):
    """获取用户的会话历史(清理过期会话)"""
    now = _time.time()
    # 清理过期会话
    expired = [uid for uid, msgs in _session_histories.items()
               if not msgs or now - msgs[-1].get('time', 0) > _SESSION_TTL]
    for uid in expired:
        del _session_histories[uid]

    return _session_histories.get(user_id, [])


def append_session(user_id, role, content):
    """向用户会话追加一条消息"""
    if user_id not in _session_histories:
        _session_histories[user_id] = []
    history = _session_histories[user_id]
    history.append({"role": role, "content": content, "time": _time.time()})
    # 超过上限截断
    if len(history) > _SESSION_MAX_TURNS * 2:
        _session_histories[user_id] = history[-(_SESSION_MAX_TURNS * 2):]


def clear_session(user_id):
    """清空用户会话"""
    if user_id in _session_histories:
        del _session_histories[user_id]


def chat(user_message, history=None, user_id=None, is_admin=False):
    """
    调用LLM API进行对话
    1. 如果传入 user_id, 使用该用户的会话历史(上下文记忆)
    2. 注入全量汇总数据
    3. 如果AI回复中包含SQL查询, 执行后补充结果再发一次
    4. 管理员(is_admin=True)时: 注入登记写库工具说明, 并执行登记操作
    """
    cfg = load_config()

    if not cfg.get('api_key'):
        return {"error": "AI未配置API Key, 请在管理员设置中配置", "config_needed": True}

    # 获取会话历史
    if user_id:
        session_history = get_session_history(user_id)
        # 追加当前用户消息到会话
        append_session(user_id, 'user', user_message)
    else:
        session_history = history or []

    data_context = build_data_context(is_admin=is_admin)
    system_content = cfg['system_prompt'] + "\n\n" + data_context

    messages = [{"role": "system", "content": system_content}]
    # 注入会话历史(只取content和role)
    for h in session_history[-_SESSION_MAX_TURNS:]:
        messages.append({"role": h.get('role', 'user'), "content": h.get('content', '')})
    messages.append({"role": "user", "content": user_message})

    api_url = _normalize_url(cfg['api_url'])
    try:
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg['model'],
                "messages": messages,
                "temperature": float(cfg.get('temperature', 0.3)),
                "max_tokens": int(cfg.get('max_tokens', 4096)),
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get('choices', [{}])[0].get('message', {}).get('content', '')

        # 循环执行数据库查询 (最多5轮, 防止AI无限查询)
        # 修复: 原代码只支持1轮查询, 第2轮回复中的[QUERY]标记会泄漏给用户
        _MAX_QUERY_ROUNDS = 5
        for _query_round in range(_MAX_QUERY_ROUNDS):
            query_results = _extract_and_run_queries(reply)
            if not query_results:
                break

            query_context = '\n'.join(query_results)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "system", "content": "以下是数据库查询结果:\n" + query_context +
                "\n请基于以上查询结果, 给用户一个完整、准确的回答。不要包含SQL语句, 直接给出分析结果。"})

            resp = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg['model'],
                    "messages": messages,
                    "temperature": float(cfg.get('temperature', 0.3)),
                    "max_tokens": int(cfg.get('max_tokens', 4096)),
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data.get('choices', [{}])[0].get('message', {}).get('content', reply)

        # 管理员: 检查并执行登记写库操作
        register_results = _extract_and_run_registers(reply, operator=user_id or 'admin') if is_admin else []
        if register_results:
            register_context = '\n'.join(register_results)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "system", "content": "以下是登记写库的执行结果:\n" + register_context +
                "\n请基于以上执行结果, 向用户确认登记是否成功。明确告知登记的电表/房间、结果(成功/重复/失败)。"
                "若登记成功, 说明该电表的故障标记已通过重算消除。不要包含标记语法, 直接用自然语言回答。"})

            resp = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg['model'],
                    "messages": messages,
                    "temperature": float(cfg.get('temperature', 0.3)),
                    "max_tokens": int(cfg.get('max_tokens', 4096)),
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data.get('choices', [{}])[0].get('message', {}).get('content', reply)

        # 保存AI回复到会话历史
        if user_id:
            append_session(user_id, 'assistant', reply)

        return {
            "reply": reply,
            "model": cfg['model'],
            "usage": data.get('usage', {}),
        }
    except requests.exceptions.Timeout:
        return {"error": "AI响应超时, 请稍后重试"}
    except requests.exceptions.ConnectionError:
        return {"error": f"无法连接AI服务: {cfg['api_url']}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"AI服务返回错误: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"AI调用异常: {str(e)}"}


def test_connection():
    """测试AI连接是否正常"""
    cfg = load_config()
    if not cfg.get('api_key'):
        return {"ok": False, "msg": "未配置API Key"}

    try:
        resp = requests.post(
            _normalize_url(cfg['api_url']),
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg['model'],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return {"ok": True, "msg": f"连接正常, 模型: {cfg['model']}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:100]}
