"""
金鹰集团数据管理中心 - 工单推送模块（独立于日报通知推送）

仿照客服小程序填报工单的链路，按项目把该项目的故障数据作为工单内容，
调用金鹰 PMS 工单系统 API 创建一条物业工单（WY_WorkSheet）。

PMS API (https://pms-api.jinying.com/api):
  - POST /WY/GetCounterInfo {guid}        -> counter_id + prj + brand + counter
  - POST /WY/GetWorkSheetType              -> 工单类型列表 (物业维修=4 / 品质管理=5 ...)
  - POST /WY/UploadFile_APP {base64图}      -> accach_id (附件)
  - POST /WY/InsertWorkSheet {str_json}     -> 建工单, 返回 q_id

调度: 每周固定 day/time 触发一次, 独立线程 + 独立 state 文件, 与 notifier 零耦合。
安全: InsertWorkSheet 是对生产 PMS 的不可逆操作, enabled 默认 false;
      首次需填 creater_phone + 确认 mapping, 并用「测试单项目」验证后再开定时。
"""
import os
import json
import time
import base64
import io
import threading
import tempfile
import requests
from datetime import datetime

from db import get_conn

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'workorder_config.json')
LINKS_FILE = os.path.join(DATA_DIR, 'workorder_links.json')       # {prj: {guid, counter_id, brand, counter}}
MAPPING_FILE = os.path.join(DATA_DIR, 'workorder_mapping.json')  # {prj: db_project_name} (短名->全名)
STATE_FILE = os.path.join(DATA_DIR, 'workorder_state.json')      # {last_send_week, saved_at}
LOG_FILE = os.path.join(DATA_DIR, 'workorder_logs.json')

DEFAULT_CONFIG = {
    "enabled": False,
    "weekly_day": 1,            # 1=周一 ... 7=周日
    "weekly_time": "09:00",
    "creater_phone": "",        # 统一服务号, 留空则推送跳过
    "pms_api": "https://pms-api.jinying.com/api",
    "projects": {},             # {prj: {"enabled": true}}  缺省视为启用
}

WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

_workorder_logs = []
_scheduler_running = False
_scheduler_thread = None
_last_send_week = None

# PMS 类型ID缓存
_types_cache = None
_types_cache_time = 0


# ─── 配置 / 数据文件 ─────────────────────────────────

def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_config():
    return _load_json(CONFIG_FILE, DEFAULT_CONFIG.copy())


def _save_config(cfg):
    _save_json(CONFIG_FILE, cfg)


def get_config():
    return _load_config()


def update_config(new_cfg):
    cfg = _load_config()
    for key in ['enabled', 'weekly_day', 'weekly_time', 'creater_phone', 'pms_api']:
        if key in new_cfg:
            cfg[key] = new_cfg[key]
    if 'projects' in new_cfg:
        cfg['projects'] = new_cfg['projects']
    _save_config(cfg)
    return cfg


def _load_links():
    return _load_json(LINKS_FILE, {})


def _save_links(links):
    _save_json(LINKS_FILE, links)


def _load_mapping():
    return _load_json(MAPPING_FILE, {})


def update_mapping(new_mapping):
    _save_json(MAPPING_FILE, new_mapping)
    return new_mapping


def get_project_options():
    """返回库中真实存在的系统项目名并集(故障表 project_name + safety_duty.unit + name_matching),
    供前端映射下拉选择, 避免手写错字。"""
    conn = get_conn()
    names = set()
    for t, col in [('ruixin_meters', 'project_name'), ('hazard_inspection', 'project_name'),
                   ('equipment_123', 'project_name'), ('water_pressure', 'project_name'),
                   ('safety_duty', 'unit')]:
        try:
            for r in conn.execute(f"SELECT DISTINCT {col} FROM {t} WHERE {col} IS NOT NULL AND {col} != ''"):
                names.add(r[0])
        except Exception:
            pass
    try:
        for r in conn.execute("SELECT DISTINCT project_name FROM name_matching WHERE project_name IS NOT NULL AND project_name != ''"):
            names.add(r[0])
    except Exception:
        pass
    conn.close()
    names.discard('测试项目')
    names.discard('')
    return sorted(names)


def _save_send_state():
    global _last_send_week
    try:
        _save_json(STATE_FILE, {'last_send_week': _last_send_week,
                                 'saved_at': datetime.now().isoformat()})
    except Exception:
        pass


# ─── 日志 ─────────────────────────────────

def _add_log(project, status, msg):
    t = datetime.now().strftime('%H:%M:%S')
    entry = {'time': t, 'date': datetime.now().strftime('%Y-%m-%d'),
             'project': project, 'status': status, 'msg': msg}
    _workorder_logs.append(entry)
    if len(_workorder_logs) > 200:
        _workorder_logs[:] = _workorder_logs[-100:]
    try:
        logs = _load_json(LOG_FILE, [])
        logs.append(entry)
        if len(logs) > 500:
            logs[:] = logs[-300:]
        _save_json(LOG_FILE, logs)
    except Exception:
        pass


def get_logs(limit=50):
    file_logs = _load_json(LOG_FILE, [])
    merged = list(file_logs)
    seen = set()
    for e in merged:
        seen.add((e.get('date', ''), e.get('time', ''), e.get('project', ''), e.get('msg', '')))
    for e in _workorder_logs:
        k = (e.get('date', ''), e.get('time', ''), e.get('project', ''), e.get('msg', ''))
        if k not in seen:
            merged.append(e)
            seen.add(k)
    return list(reversed(merged[-limit:])) if merged else []


# ─── PMS 客户端 ─────────────────────────────────

def _pms_post(cfg, endpoint, data, timeout=30):
    base = cfg.get('pms_api') or DEFAULT_CONFIG['pms_api']
    url = base.rstrip('/') + endpoint
    resp = requests.post(url, data=data,
                         headers={'Content-Type': 'application/x-www-form-urlencoded',
                                  'User-Agent': 'Mozilla/5.0'},
                         timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_counter_info(cfg, guid):
    """guid -> {id, prj, brand, counter} 或 None"""
    try:
        data = _pms_post(cfg, '/WY/GetCounterInfo', {'guid': guid})
        d = data.get('data')
        return d if d else None
    except Exception as e:
        _add_log('pms', 'error', f'GetCounterInfo 失败 guid={guid[:8]}..: {str(e)[:80]}')
        return None


def get_worksheet_types(cfg, refresh=False):
    """工单类型列表, 缓存1小时"""
    global _types_cache, _types_cache_time
    if _types_cache and not refresh and time.time() - _types_cache_time < 3600:
        return _types_cache
    try:
        data = _pms_post(cfg, '/WY/GetWorkSheetType', {})
        types = data.get('data') or []
        if types:
            _types_cache = types
            _types_cache_time = time.time()
        return types
    except Exception as e:
        _add_log('pms', 'error', f'GetWorkSheetType 失败: {str(e)[:80]}')
        return _types_cache or []


def _resolve_type_id(cfg, type_name):
    """物业维修/品质管理 -> typeId, 找不到回退第一个"""
    types = get_worksheet_types(cfg) or []
    for t in types:
        n = t.get('wy_type_name', '')
        if n == type_name or (n and type_name in n) or (n and n in type_name):
            return t.get('wy_type_id')
    return types[0].get('wy_type_id') if types else None


def upload_image(cfg, png_bytes):
    """PNG 字节 -> accach_id (PMS 附件)。返回 accach_id 或 None"""
    b64 = base64.b64encode(png_bytes).decode()
    data_url = 'data:image/jpeg;base64,' + b64
    # 文件名: 随机 guid.jpg (仿小程序)
    import uuid
    fname = str(uuid.uuid4()).replace('-', '')[:32] + '.jpg'
    try:
        resp = _pms_post(cfg, '/WY/UploadFile_APP',
                         {'base64Str': data_url, 'fileName': fname, 'type': 0, 'creater_id': ''})
        if str(resp.get('code', '')) == '-1':
            _add_log('pms', 'error', f'UploadFile_APP 失败: {str(resp.get("msg",""))[:80]}')
            return None
        d = resp.get('data')
        if isinstance(d, str):
            d = json.loads(d)
        accach_id = d.get('accach_id') if isinstance(d, dict) else None
        return accach_id
    except Exception as e:
        _add_log('pms', 'error', f'UploadFile_APP 异常: {str(e)[:80]}')
        return None


def insert_worksheet(cfg, q_content, wy_type, counter_id, creater_phone, accach_ids):
    """建工单, 返回 (q_id, err)。err 为 None 表示成功。
    不自动重试: PMS 无响应可能是已建单但丢包, 重试会重复建单。"""
    payload = {
        'q_title': '',
        'q_content': q_content,
        'q_state': '0',
        'wy_type': str(wy_type),
        'oper_name': '', 'oper_id': '',
        'state': 0,
        'creater_phone': creater_phone,
        'counter_id': int(counter_id),
        'ACCACHID_Lst': accach_ids or [],
    }
    str_json = json.dumps(payload, ensure_ascii=False)
    base = (cfg.get('pms_api') or DEFAULT_CONFIG['pms_api']).rstrip('/')
    try:
        resp = requests.post(base + '/WY/InsertWorkSheet',
                             data={'str_json': str_json},
                             headers={'Content-Type': 'application/x-www-form-urlencoded',
                                      'User-Agent': 'Mozilla/5.0'},
                             timeout=30)
        txt = (resp.text or '').strip()
        if not txt:
            return None, 'PMS 无响应(可能临时/限流), 工单状态未知, 未重试以免重复'
        try:
            data = json.loads(txt)
        except Exception:
            return None, f'PMS 响应非JSON: {txt[:80]}'
        if str(data.get('code', '')) == '-1':
            return None, f'PMS 拒绝: {str(data.get("msg",""))[:80]}'
        d = data.get('data')
        if isinstance(d, str) and d:
            try:
                d = json.loads(d)
            except Exception:
                pass
        q_id = d.get('q_id') if isinstance(d, dict) else None
        return q_id, None
    except Exception as e:
        return None, f'InsertWorkSheet 异常: {str(e)[:80]}'


# ─── 故障数据 → 工单内容 + 明细图 ─────────────────────────────────

def _query_faults(db_project_name):
    """复用 notifier._build_fault_detail_xlsx 的 SQL, 取该项目的故障明细行。
    返回 {'meters':[], 'safety':[], 'duty':[], 'water':[], 'equipment':[]}"""
    conn = get_conn()
    out = {'meters': [], 'safety': [], 'duty': [], 'water': [], 'equipment': []}
    try:
        out['meters'] = conn.execute("""
            SELECT device_id, building, floor, room, comm_status, device_status,
                   fault_tag, fault_desc, balance
            FROM ruixin_meters
            WHERE project_name=? AND (fault_tag IS NOT NULL AND fault_tag != '')
            ORDER BY fault_tag, device_id
        """, (db_project_name,)).fetchall()
        out['safety'] = conn.execute("""
            SELECT category, level, responsible, description, hazard_status,
                   remaining_days, create_time
            FROM hazard_inspection
            WHERE project_name=? AND create_days <= 31 AND hazard_status != '已整改'
            ORDER BY level, remaining_days
        """, (db_project_name,)).fetchall()
        out['duty'] = conn.execute("""
            SELECT plan_type, plan_content, responsible, plan_status, countdown,
                   start_date, end_date
            FROM safety_duty
            WHERE unit=? AND plan_status='已逾期'
        """, (db_project_name,)).fetchall()
        out['water'] = conn.execute("""
            SELECT device_no, device_name, install_loc, pressure, pressure_fault,
                   report_time, comm_delay, online_status
            FROM water_pressure
            WHERE project_name=? AND (pressure_fault='失压' OR pressure_fault='超压')
        """, (db_project_name,)).fetchall()
        out['equipment'] = conn.execute("""
            SELECT device_id, device_name, device_type, device_group, online_status,
                   device_status, last_comm, comm_delay
            FROM equipment_123
            WHERE project_name=? AND comm_delay >= 90
            ORDER BY comm_delay DESC
        """, (db_project_name,)).fetchall()
    finally:
        conn.close()
    return out


def _v(r, *keys):
    """从 sqlite3.Row 取多个字段, 返回去空格字符串"""
    vals = []
    for k in keys:
        x = r[k] if k in r.keys() else None
        vals.append(str(x) if x is not None and x != '' else '')
    return vals


def build_fault_content(db_project_name):
    """构建 q_content 文本 + wy_type + 明细图 PNG 字节。
    无任何故障返回 None。"""
    faults = _query_faults(db_project_name)
    n_m = len(faults['meters'])
    n_s = len(faults['safety'])
    n_d = len(faults['duty'])
    n_w = len(faults['water'])
    n_e = len(faults['equipment'])
    if (n_m + n_s + n_d + n_w + n_e) == 0:
        return None

    lines = []
    # 标题
    lines.append(f'【系统运行监管·数据管理中心】{db_project_name} 故障周报汇总 {datetime.now().strftime("%Y-%m-%d")}')
    lines.append('')

    if n_m:
        lines.append(f'【瑞信电表】故障 {n_m} 块：')
        for r in faults['meters'][:30]:
            did, bld, flr, rm, ft, fd = _v(r, 'device_id', 'building', 'floor', 'room', 'fault_tag', 'fault_desc')
            loc = ''.join(x for x in [bld, flr, rm] if x)
            lines.append(f'  · {ft or "故障"} {fd} | {loc} | 表号{did}')
        if n_m > 30:
            lines.append(f'  …其余 {n_m-30} 块详见数据中心')
        lines.append('')

    if n_s:
        lines.append(f'【金鹰安全】隐患 {n_s} 条：')
        for r in faults['safety'][:30]:
            lv, cat, desc, resp, days = _v(r, 'level', 'category', 'description', 'responsible', 'remaining_days')
            lines.append(f'  · [{lv or cat or "隐患"}] {desc} | 责任人{resp} | 剩余{days}天')
        if n_s > 30:
            lines.append(f'  …其余 {n_s-30} 条详见数据中心')
        lines.append('')

    if n_d:
        lines.append(f'【安全履职】逾期 {n_d} 条：')
        for r in faults['duty'][:20]:
            pt, pc, resp = _v(r, 'plan_type', 'plan_content', 'responsible')
            lines.append(f'  · {pt} {pc} | 责任人{resp}')
        lines.append('')

    if n_w:
        lines.append(f'【水压异常】{n_w} 处：')
        for r in faults['water'][:20]:
            pf, dn, loc, pr = _v(r, 'pressure_fault', 'device_name', 'install_loc', 'pressure')
            lines.append(f'  · {pf} {dn} {loc} 压力{pr}')
        lines.append('')

    if n_e:
        lines.append(f'【123设备】故障 {n_e} 台：')
        for r in faults['equipment'][:30]:
            did, dn, dt, cd = _v(r, 'device_id', 'device_name', 'device_type', 'comm_delay')
            lines.append(f'  · {dn or dt} 表号{did} | 通讯时差{cd}天')
        if n_e > 30:
            lines.append(f'  …其余 {n_e-30} 台详见数据中心')
        lines.append('')

    lines.append('— 以上故障明细由金鹰数据管理中心自动汇总生成 —')

    # wy_type: 统一用物业维修(4)
    wy_type_name = '物业维修'

    # q_content 用精简摘要(PMS q_content 长度上限~500字符), 完整明细见附件图
    s = [f'【系统运行监管·数据管理中心】{db_project_name} 故障周报汇总 {datetime.now().strftime("%Y-%m-%d")}', '']
    if n_m:
        s.append(f'【瑞信电表】故障{n_m}块：')
        for r in faults['meters'][:3]:
            ft, fd, did = _v(r, 'fault_tag', 'fault_desc', 'device_id')
            s.append(f'  · {ft or "故障"} {fd} | 表号{did}')
        if n_m > 3:
            s.append(f'  …等共{n_m}块')
    if n_s:
        s.append(f'【金鹰安全】隐患{n_s}条：')
        for r in faults['safety'][:3]:
            lv, desc, resp = _v(r, 'level', 'description', 'responsible')
            s.append(f'  · [{lv or "隐患"}] {desc} | {resp}')
        if n_s > 3:
            s.append(f'  …等共{n_s}条')
    if n_d:
        s.append(f'【安全履职】逾期{n_d}条')
    if n_w:
        s.append(f'【水压异常】{n_w}处')
    if n_e:
        s.append(f'【123设备】故障{n_e}台')
    s.append('')
    s.append('完整故障明细见附件图。')
    q_content = '\n'.join(s)
    if len(q_content) > 480:
        q_content = q_content[:458] + '\n…完整明细见附件图'

    # 附件图用完整明细(lines), 不受 q_content 长度限制
    png = _render_fault_image(db_project_name, lines)
    return {
        'q_content': q_content,
        'wy_type_name': wy_type_name,
        'png': png,
        'counts': {'meters': n_m, 'safety': n_s, 'duty': n_d, 'water': n_w, 'equipment': n_e},
    }


def _load_cjk_font(size):
    """尝试加载支持中文的 TTF, 找不到回退默认(中文会变方块)"""
    from PIL import ImageFont
    candidates = [
        r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyhbd.ttc',
        r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\simsun.ttc',
        r'C:\Windows\Fonts\YaHeiConsolasHybrid.ttf',
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _render_fault_image(project_name, lines):
    """把故障明细文本渲染成 PNG, 返回字节"""
    from PIL import Image, ImageDraw
    font = _load_cjk_font(20)
    title_font = _load_cjk_font(24)
    line_h = 28
    pad = 24
    width = 760
    height = pad * 2 + 40 + line_h * len(lines) + 20
    img = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # 顶栏
    draw.rectangle([0, 0, width, 48], fill=(47, 84, 150))
    draw.text((pad, 11), f'{project_name} 故障明细汇总', fill=(255, 255, 255), font=title_font)
    y = 60
    for ln in lines:
        # 简单自动换行 (先清掉 DB 文本里可能混入的换行, 避免 textlength 报错)
        seg = ln.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
        # 估算宽度: 中文约20px, 英文约11px
        max_w = width - pad * 2
        cur = ''
        for ch in seg:
            cur2 = cur + ch
            w = draw.textlength(cur2, font=font)
            if w > max_w and cur:
                draw.text((pad, y), cur, fill=(51, 51, 51), font=font)
                y += line_h
                cur = ch
            else:
                cur = cur2
        if cur:
            draw.text((pad, y), cur, fill=(51, 51, 51), font=font)
        y += line_h
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


# ─── 发送 ─────────────────────────────────

def send_workorder(prj):
    """向单个项目(prj=短名)创建工单。返回 {success/message/q_id} 或 {error}"""
    cfg = _load_config()
    links = _load_links()
    mapping = _load_mapping()

    link = links.get(prj)
    if not link:
        return {'error': f'未找到该项目链接: {prj}'}
    counter_id = link.get('counter_id')
    guid = link.get('guid', '')
    if not counter_id:
        return {'error': f'该项目无 counter_id (guid={guid[:8]}..), 请刷新链接'}

    db_project_name = mapping.get(prj, '')
    if not db_project_name:
        _add_log(prj, 'error', '未配置名称映射 (workorder_mapping), 跳过')
        return {'error': f'未配置名称映射, 请先在 mapping 中补 {prj} 对应的系统项目名'}

    content = build_fault_content(db_project_name)
    if not content:
        _add_log(prj, 'info', f'{prj} 无故障数据, 跳过 (不发空工单)')
        return {'skipped': True, 'message': f'{prj} 无故障数据, 不发空工单'}

    creater_phone = cfg.get('creater_phone', '').strip()
    if not creater_phone:
        _add_log(prj, 'error', 'creater_phone 未配置, 跳过')
        return {'error': 'creater_phone 未配置, 请先在工单推送配置中填写统一服务号'}

    pms_api = cfg.get('pms_api') or DEFAULT_CONFIG['pms_api']
    wy_type = _resolve_type_id(cfg, content['wy_type_name'])
    if not wy_type:
        _add_log(prj, 'error', '未取到工单类型ID (GetWorkSheetType)')
        return {'error': '未取到工单类型ID'}

    # 1) 上传明细图
    accach_id = upload_image(cfg, content['png'])
    if not accach_id:
        _add_log(prj, 'error', '附件图片上传失败, 工单未提交')
        return {'error': '附件图片上传失败, 工单未提交'}
    _add_log(prj, 'info', f'附件上传成功 accach_id={accach_id}')

    # 2) 建工单
    q_id, err = insert_worksheet(
        cfg, content['q_content'], wy_type, counter_id, creater_phone, [accach_id])
    if not q_id:
        _add_log(prj, 'error', f'工单提交失败: {err}')
        return {'error': f'工单提交失败: {err}'}
    _add_log(prj, 'success', f'工单已创建 q_id={q_id} 类型={content["wy_type_name"]}({wy_type}) '
                             f'故障: {content["counts"]}')
    return {'success': True, 'q_id': q_id,
            'message': f'工单已创建: {prj} q_id={q_id} (类型:{content["wy_type_name"]})'}


def send_all_workorders():
    """遍历所有 enabled 且 mapping 已配的项目创建工单"""
    cfg = _load_config()
    links = _load_links()
    mapping = _load_mapping()
    projects = cfg.get('projects', {})
    creater_phone = cfg.get('creater_phone', '').strip()

    results = []
    for prj in links.keys():
        pcfg = projects.get(prj, {})
        if pcfg.get('enabled', True) is False:
            continue
        if not mapping.get(prj):
            results.append({'project': prj, 'skipped': True, 'message': '未配置名称映射'})
            continue
        if not creater_phone:
            results.append({'project': prj, 'skipped': True, 'message': 'creater_phone 未配置'})
            continue
        try:
            r = send_workorder(prj)
            results.append({'project': prj, **r})
        except Exception as e:
            _add_log(prj, 'error', f'推送异常: {str(e)[:80]}')
            results.append({'project': prj, 'error': str(e)[:100]})
        time.sleep(2)  # 避免压 PMS
    _add_log('scheduler', 'info',
             f'本周工单推送完成: {len(results)}项 (成功{sum(1 for x in results if x.get("success"))}/'
             f'跳过{sum(1 for x in results if x.get("skipped"))}/失败{sum(1 for x in results if x.get("error"))})')
    return {'results': results, 'total': len(results)}


def refresh_links():
    """对所有已存 guid 重新拉取 counter_id (只读, 无副作用)"""
    cfg = _load_config()
    links = _load_links()
    updated = {}
    for prj, link in links.items():
        guid = link.get('guid')
        if not guid:
            updated[prj] = link
            continue
        info = get_counter_info(cfg, guid)
        if info:
            updated[prj] = {'guid': guid, 'counter_id': info.get('id'),
                            'prj': info.get('prj', prj), 'brand': info.get('brand'),
                            'counter': info.get('counter')}
        else:
            updated[prj] = link  # 保留旧值
        time.sleep(0.3)
    _save_links(updated)
    _add_log('pms', 'info', f'刷新链接完成: {len(updated)}项')
    return updated


# ─── 调度器 (每周) ─────────────────────────────────

def scheduler_start():
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return {'message': '工单调度器已在运行'}
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_workorder_loop, daemon=True)
    _scheduler_thread.start()
    _add_log('scheduler', 'info', '工单调度器已启动')
    return {'message': '工单调度器已启动'}


def scheduler_stop():
    global _scheduler_running
    _scheduler_running = False
    _add_log('scheduler', 'info', '工单调度器已停止')
    return {'message': '工单调度器已停止'}


def scheduler_is_active():
    return _scheduler_running


def _week_key(now):
    iso = now.isocalendar()  # (year, week, weekday)
    return f'{iso[0]}-W{iso[1]:02d}'


def _workorder_loop():
    global _scheduler_running, _last_send_week
    _scheduler_running = True
    _add_log('scheduler', 'info', '工单调度循环开始')

    # 启动恢复 state
    try:
        st = _load_json(STATE_FILE, {})
        _last_send_week = st.get('last_send_week')
        _add_log('scheduler', 'info', f'恢复推送状态: last_send_week={_last_send_week}')
    except Exception as e:
        _add_log('scheduler', 'error', f'恢复 state 失败: {str(e)[:80]}')

    # 启动补推: enabled 且本周还没推过 -> 立即补推
    try:
        cfg0 = _load_config()
        wk0 = _week_key(datetime.now())
        if cfg0.get('enabled') and _last_send_week != wk0:
            _add_log('scheduler', 'info', '启动补推: 本周尚未推送, 立即执行')
            _last_send_week = wk0
            _save_send_state()
            try:
                send_all_workorders()
            except Exception as e:
                _add_log('scheduler', 'error', f'启动补推异常: {str(e)[:80]}')
                _last_send_week = None
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
            target_day = int(cfg.get('weekly_day', 1))
            target_time = str(cfg.get('weekly_time', '09:00')).strip()
            wk = _week_key(now)

            # 周几 + HH:MM 匹配 且 本周没推过
            if (now.weekday() + 1) == target_day \
                    and now.strftime('%H:%M') == target_time \
                    and _last_send_week != wk:
                _last_send_week = wk
                _save_send_state()
                _add_log('scheduler', 'info',
                         f'开始本周工单推送 ({WEEKDAY_NAMES[target_day-1]} {target_time})')
                try:
                    send_all_workorders()
                except Exception as e:
                    _add_log('scheduler', 'error', f'本周推送异常: {str(e)[:80]}')
                    _last_send_week = None
                    _save_send_state()

            time.sleep(30)
        except Exception as e:
            _add_log('scheduler', 'error', f'调度异常: {str(e)[:80]}')
            time.sleep(60)
