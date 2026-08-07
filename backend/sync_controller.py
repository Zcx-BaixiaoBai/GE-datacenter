"""
金鹰集团数据管理中心 - 数据同步控制器
直接 import 爬虫模块, 执行: 爬取 → 生成xlsx → 导入SQLite

模块:
  ruixin  - 瑞信电表 (瑞信平台)
  budget  - 预算管理 (泛微OA)
  sd123   - 123物联网设备
  jy      - 金鹰安全管理
"""
import os
import sys
import json
import time
import threading
import subprocess
from datetime import datetime

# 集控中心爬虫目录
CRAWLER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crawlers')
if CRAWLER_DIR not in sys.path:
    sys.path.insert(0, CRAWLER_DIR)

# 爬虫输出目录 (xlsx)
DATA_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', '集控数据')
os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CRAWLER_DIR, 'config.json')
SYNC_CONFIG_FILE = os.path.join(CRAWLER_DIR, 'sync_config.json')

# 爬虫内部的 data 目录 (cache等)
CRAWLER_DATA_DIR = os.path.join(CRAWLER_DIR, 'data')
os.makedirs(CRAWLER_DATA_DIR, exist_ok=True)

# 同步日志 (内存)
_sync_logs = []
_sync_running = {}

# 调度器状态
_scheduler_running = False
_scheduler_thread = None
_next_run = {}

# 模块配置
MODULES = {
    'ruixin': {
        'name': '瑞信电表',
        'output': os.path.join(DATA_OUTPUT_DIR, '瑞信电表.xlsx'),
        'sheet_aliases': {'瑞信数据': 'ruixin'},
    },
    'budget': {
        'name': '预算管理',
        'output': os.path.join(DATA_OUTPUT_DIR, '预算报表.xlsx'),
        'sheet_aliases': {'经营类预算': '物业预算', '商贸类预算': '商贸预算', '预算统计汇总': '预算使用情况'},
    },
    'sd123': {
        'name': '123物联网设备',
        'output': os.path.join(DATA_OUTPUT_DIR, '设备信息.xlsx'),
        'sheet_aliases': {'设备信息汇总': '123'},
    },
    'jy': {
        'name': '金鹰安全管理',
        'output': os.path.join(DATA_OUTPUT_DIR, '金鹰安全管理.xlsx'),
        'sheet_aliases': {'隐患治理': '隐患核查', '消防水监测': '末端水压'},
    },
}


def _add_log(module, msg, type='info'):
    t = datetime.now().strftime('%H:%M:%S')
    _sync_logs.append({'time': t, 'module': module, 'msg': msg, 'type': type})
    if len(_sync_logs) > 200:
        _sync_logs[:] = _sync_logs[-100:]


def get_logs(limit=50):
    return list(reversed(_sync_logs[-limit:]))


def _load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _load_sync_config():
    default = {f'{mid}_interval_min': 0 for mid in MODULES}
    default.update({f'{mid}_output_path': MODULES[mid]['output'] for mid in MODULES})
    if os.path.exists(SYNC_CONFIG_FILE):
        try:
            with open(SYNC_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**default, **json.load(f)}
        except:
            pass
    return default


def _save_sync_config(cfg):
    with open(SYNC_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_status():
    """获取所有同步模块状态"""
    sync_cfg = _load_sync_config()
    result = []
    for mid, info in MODULES.items():
        interval = sync_cfg.get(f'{mid}_interval_min', 0)
        next_t = _next_run.get(mid, 0)
        remaining = max(0, next_t - time.time()) if next_t > 0 and interval > 0 else -1
        result.append({
            'id': mid,
            'name': info['name'],
            'running': _sync_running.get(mid, False),
            'interval_min': interval,
            'scheduler_active': _scheduler_running and interval > 0,
            'remaining_sec': round(remaining) if remaining >= 0 else -1,
            'next_run': datetime.fromtimestamp(next_t).strftime('%H:%M:%S') if next_t > 0 and interval > 0 else None,
            'output_exists': os.path.exists(info['output']),
            'output_path': info['output'],
        })
    return result


def update_sync_config(new_cfg):
    """更新同步配置(管理员)"""
    cfg = _load_sync_config()
    for key in ['ruixin_interval_min', 'budget_interval_min', 'sd123_interval_min', 'jy_interval_min']:
        if key in new_cfg:
            cfg[key] = int(new_cfg[key])
    _save_sync_config(cfg)
    return cfg


def trigger_sync(module_id):
    """触发单个模块同步 (异步)"""
    if module_id not in MODULES:
        return {'error': f'未知模块: {module_id}'}
    if _sync_running.get(module_id, False):
        return {'error': f'{MODULES[module_id]["name"]} 正在同步中'}
    thread = threading.Thread(target=_run_sync, args=(module_id,), daemon=True)
    thread.start()
    return {'message': f'已触发 {MODULES[module_id]["name"]} 同步'}


def trigger_all_sync():
    """触发所有模块同步"""
    results = []
    for mid in MODULES:
        if not _sync_running.get(mid, False):
            t = threading.Thread(target=_run_sync, args=(mid,), daemon=True)
            t.start()
            results.append(f'{MODULES[mid]["name"]} 已触发')
        else:
            results.append(f'{MODULES[mid]["name"]} 跳过(运行中)')
    return {'message': '; '.join(results)}


# ═══════════════════════════════════════
#  xlsx 导出函数 (从集控中心 app.py 搬移)
# ═══════════════════════════════════════

def _rx_save_xlsx(records, filepath):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    if not records:
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "瑞信数据"
    all_keys = list(records[0].keys())
    h_font = Font(bold=True, size=10, color="FFFFFF")
    h_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(top=thin, left=thin, right=thin, bottom=thin)
    for ci, label in enumerate(all_keys, 1):
        cell = ws.cell(row=1, column=ci, value=label)
        cell.font = h_font; cell.fill = h_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    for ri, r in enumerate(records, 2):
        for ci, key in enumerate(all_keys, 1):
            cell = ws.cell(row=ri, column=ci, value=r.get(key, ""))
            cell.border = border
    for ci in range(1, len(all_keys) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 14
    ws.auto_filter.ref = f"A1:{get_column_letter(len(all_keys))}{len(records)+1}"
    ws.freeze_panes = "A2"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)


def _budget_save_xlsx(report1, report2, filepath):
    import re as _re
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    if not report1 and not report2:
        return
    _CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}
    def _pk(p):
        m = _re.search(r'(\d{4})(.+)', p)
        return (int(m.group(1)), _CN.get(m.group(2).rstrip('期'), 99)) if m else (0,0)
    def _num(v):
        try: return float(str(v).replace(',','').strip() or 0)
        except: return 0.0
    def _pct(a, b):
        return f'{a/b*100:.1f}%' if b else '—'
    def _build_raw(data):
        out = {}
        for r in data:
            u,p,c = r['预算单位'],r['预算期间'],r['预算科目']
            a = _num(r.get('实际发生数',0)) + _num(r.get('审批中费用',0))
            b = _num(r.get('追加后预算数',0))
            out.setdefault(u,{}).setdefault(p,{}).setdefault(c,[0.0,0.0])
            out[u][p][c][0]+=a; out[u][p][c][1]+=b
        return out
    def _sum_periods(raw, unit, periods):
        res = {}
        for p in periods:
            if p in raw.get(unit,{}):
                for c,(a,b) in raw[unit][p].items():
                    res.setdefault(c,[0.0,0.0]); res[c][0]+=a; res[c][1]+=b
        return res
    def _sum_all(raw, periods):
        res = {}
        for unit in raw:
            for p in periods:
                if p in raw.get(unit,{}):
                    for c,(a,b) in raw[unit][p].items():
                        res.setdefault(c,[0.0,0.0]); res[c][0]+=a; res[c][1]+=b
        return res

    all_periods = sorted({r['预算期间'] for r in report1+report2}, key=_pk)
    raw1 = _build_raw(report1)
    raw2 = _build_raw(report2)
    units1 = sorted(raw1)
    units2 = sorted(raw2)

    wb = Workbook()
    thin = Side(style='thin', color='D9D9D9')
    border = Border(top=thin, left=thin, right=thin, bottom=thin)
    h_font = Font(bold=True, size=10, color='FFFFFF')
    h_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    hdr_align = Alignment(horizontal='center', vertical='center')

    for title, raw, units in [('经营类预算', raw1, units1), ('商贸类预算', raw2, units2)]:
        if not raw:
            continue
        ws = wb.create_sheet(title)
        # 表头: 科目 | 各单位合计 | 各期间...
        headers = ['预算科目'] + [f'{u}合计' for u in units] + all_periods
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=ci, value=h)
            c.font = h_font; c.fill = h_fill; c.alignment = hdr_align; c.border = border
        # 汇总
        all_sums = _sum_all(raw, all_periods)
        cats = sorted(all_sums)
        for ri, cat in enumerate(cats, 2):
            ws.cell(row=ri, column=1, value=cat).border = border
            for ci, u in enumerate(units, 2):
                us = _sum_periods(raw, u, all_periods)
                a, b = us.get(cat, [0, 0])
                ws.cell(row=ri, column=ci, value=_pct(a, b)).border = border
            for ci_off, p in enumerate(all_periods):
                a, b = all_sums.get(cat, [0, 0])
                ws.cell(row=ri, column=len(units) + 2 + ci_off, value=_pct(a, b)).border = border
        for ci in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 14
        ws.freeze_panes = 'B2'

    # 预算统计汇总
    ws3 = wb.create_sheet('预算统计汇总')
    ws3.cell(row=1, column=1, value='预算单位').font = h_font
    ws3.cell(row=1, column=2, value='合计执行率').font = h_font
    for ci in range(1, 3):
        ws3.cell(row=1, column=ci).fill = h_fill
        ws3.cell(row=1, column=ci).alignment = hdr_align
        ws3.cell(row=1, column=ci).border = border
    all_units = sorted(set(units1) | set(units2))
    for ri, u in enumerate(all_units, 2):
        s1 = _sum_periods(raw1, u, all_periods)
        s2 = _sum_periods(raw2, u, all_periods)
        merged = {}
        for c, (a, b) in s1.items():
            merged.setdefault(c, [0, 0]); merged[c][0]+=a; merged[c][1]+=b
        for c, (a, b) in s2.items():
            merged.setdefault(c, [0, 0]); merged[c][0]+=a; merged[c][1]+=b
        ta = sum(v[0] for v in merged.values())
        tb = sum(v[1] for v in merged.values())
        ws3.cell(row=ri, column=1, value=u).border = border
        ws3.cell(row=ri, column=2, value=_pct(ta, tb)).border = border
    for ci in range(1, 3):
        ws3.column_dimensions[get_column_letter(ci)].width = 18
    ws3.freeze_panes = 'A2'

    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)


def _jy_save_xlsx(plan_data, risk_data, fire_data, filepath):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    thin = Side(style='thin', color='D9D9D9')
    border = Border(top=thin, left=thin, right=thin, bottom=thin)
    h_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    h_font = Font(bold=True, size=10, color='FFFFFF')
    wb = Workbook()
    for sheet_name, records in [('安全履职', plan_data), ('隐患治理', risk_data), ('消防水监测', fire_data)]:
        if not records:
            continue
        ws = wb.create_sheet(sheet_name)
        keys = list(records[0].keys())
        for ci, k in enumerate(keys, 1):
            c = ws.cell(row=1, column=ci, value=k)
            c.font, c.fill, c.alignment, c.border = h_font, h_fill, Alignment(horizontal='center'), border
        for ri, row in enumerate(records, 2):
            for ci, k in enumerate(keys, 1):
                c = ws.cell(row=ri, column=ci, value=row.get(k, ''))
                c.border = border
        for ci in range(1, len(keys) + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 16
        ws.freeze_panes = 'A2'
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']
    wb.save(filepath)


# ═══════════════════════════════════════
#  各模块同步逻辑 (从集控中心 app.py 搬迁)
# ═══════════════════════════════════════

def _sync_ruixin(output_path):
    import ruixin_crawler as rx
    cfg = _load_config()["ruixin"]
    token = rx.ensure_token(cfg)
    raw = rx.fetch_data(cfg, token)
    records = rx.extract_records(raw)
    rx.cache_data(records)
    records = rx.load_cache()
    if records:
        _rx_save_xlsx(records, output_path)
    return len(records)


def _sync_budget(output_path):
    import budget_crawler as bc
    bc.crawl_all()
    r1 = bc.load_report(1)
    r2 = bc.load_report(2)
    if r1 or r2:
        _budget_save_xlsx(r1, r2, output_path)
    return len(r1) + len(r2)


def _sync_sd123(output_path):
    import sd123_crawler as s123
    devices, projects = s123.crawl_all()
    # 合并 MQTT 实时数据
    _MQTT_FIELDS = {'温度', '湿度', '水浸状态', '外部供电', '电池电量',
                    '信号强度', '上报时间', '最后更新时间', '噪声值', '压力',
                    '甲醛浓度', 'PM2.5浓度', 'TVOC浓度', 'CO2浓度'}
    try:
        import sd123_mqtt
        rt = sd123_mqtt.get_realtime()
        rt_devs = rt.get('devices', {})
        for dev in devices:
            devid = dev.get('设备ID', '')
            rt_dev = rt_devs.get(devid)
            if rt_dev:
                for k in _MQTT_FIELDS:
                    if k in rt_dev and k not in dev:
                        dev[k] = rt_dev[k]
    except Exception:
        pass
    if devices:
        s123.export_xlsx(devices, output_path)
    return len(devices)


def _sync_jy(output_path):
    import jinying_crawler as jy
    jy.sync_all()
    plan_data = jy.load_plan()
    risk_data = jy.load_risk()
    fire_data = jy.load_fire()
    if plan_data or risk_data or fire_data:
        _jy_save_xlsx(plan_data, risk_data, fire_data, output_path)
    return len(plan_data) + len(risk_data) + len(fire_data)


_SYNC_FUNCS = {
    'ruixin': _sync_ruixin,
    'budget': _sync_budget,
    'sd123':  _sync_sd123,
    'jy':     _sync_jy,
}


# ═══════════════════════════════════════
#  执行同步
# ═══════════════════════════════════════

def _run_sync(module_id):
    """执行同步: 爬虫采集 → 生成xlsx → 导入SQLite"""
    info = MODULES[module_id]
    func = _SYNC_FUNCS[module_id]
    _sync_running[module_id] = True
    _add_log(module_id, f'开始同步 [{info["name"]}]...')

    start_time = time.time()

    try:
        # 1. 爬取 + 生成 xlsx
        _add_log(module_id, '正在爬取数据...')
        count = func(info['output'])
        _add_log(module_id, f'爬取完成, {count} 条记录')

        # 2. 导入 xlsx 到 SQLite
        output_xlsx = info['output']
        if not os.path.exists(output_xlsx):
            _add_log(module_id, f'输出文件不存在: {output_xlsx}', 'error')
            _sync_running[module_id] = False
            return

        _add_log(module_id, '开始导入数据库...')
        from sync import sync_from_xlsx
        sync_result = sync_from_xlsx(
            output_xlsx, do_reset=False,
            sheet_aliases=info.get('sheet_aliases')
        )

        if sync_result.get('success'):
            duration = round(time.time() - start_time, 1)
            _add_log(module_id, f'同步完成: {sync_result["total_rows"]}行, 耗时{duration}秒', 'success')
        else:
            _add_log(module_id, f'导入失败: {sync_result.get("errors", [])}', 'error')

    except Exception as e:
        duration = round(time.time() - start_time, 1)
        _add_log(module_id, f'同步失败: {str(e)} ({duration}秒)', 'error')
    finally:
        _sync_running[module_id] = False


# ═══════════════════════════════════════
#  调度器
# ═══════════════════════════════════════

def scheduler_start():
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return {'message': '调度器已在运行'}
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    _add_log('scheduler', '调度器已启动')
    return {'message': '调度器已启动'}


def scheduler_stop():
    global _scheduler_running
    _scheduler_running = False
    _add_log('scheduler', '调度器已停止')
    return {'message': '调度器已停止'}


def scheduler_is_active():
    return _scheduler_running


def _scheduler_loop():
    global _scheduler_running
    _scheduler_running = True
    sync_cfg = _load_sync_config()
    now = time.time()
    for mid in MODULES:
        interval = sync_cfg.get(f'{mid}_interval_min', 0)
        if interval > 0:
            _next_run[mid] = now
    _add_log('scheduler', '调度循环开始')

    while _scheduler_running:
        try:
            sync_cfg = _load_sync_config()
            now = time.time()
            for mid in MODULES:
                interval = sync_cfg.get(f'{mid}_interval_min', 0)
                if interval <= 0:
                    continue
                next_t = _next_run.get(mid, 0)
                if now >= next_t and not _sync_running.get(mid, False):
                    _run_sync(mid)
                    _next_run[mid] = time.time() + interval * 60
            time.sleep(10)
        except Exception as e:
            _add_log('scheduler', f'调度异常: {e}', 'error')
            time.sleep(5)
