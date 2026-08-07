"""
金鹰安全管理系统爬虫模块
系统: http://safety.jinying.com:18181
功能: 安全履职 / 隐患治理 / 消防水监测

API:
- 安全履职计划: GET /api/planOwn/search
- 隐患治理: GET /api/allRisk/page
- 消防水监测: GET /api/device/data/water/page
认证: Authorization: Bearer {token}
"""
import requests
import json
import time
import os
import shutil
from datetime import datetime

BASE_URL = 'http://safety.jinying.com:18181'

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_DIR, 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'jinying')

# Token 缓存：优先用本地的（随项目备份），找不到才去原始位置
_WPS_ROOT = r'C:\Users\Administrator\.copaw\workspaces\wps'
TOKEN_CACHE_LOCAL = os.path.join(DATA_DIR, 'jinying_token.json')
TOKEN_CACHE_ORIG = os.path.join(_WPS_ROOT, '金鹰安全管理系统数据爬取工具', 'token_cache.json')

os.makedirs(CACHE_DIR, exist_ok=True)


# ── Token ──

def _get_token_path():
    if os.path.exists(TOKEN_CACHE_LOCAL):
        return TOKEN_CACHE_LOCAL
    if os.path.exists(TOKEN_CACHE_ORIG):
        shutil.copy(TOKEN_CACHE_ORIG, TOKEN_CACHE_LOCAL)
        print(f'[jinying] Token已复制到本地: {TOKEN_CACHE_LOCAL}')
        return TOKEN_CACHE_LOCAL
    # Token 文件不存在，自动登录获取
    _auto_login_refresh()
    return TOKEN_CACHE_LOCAL


def _auto_login_refresh():
    """用 Playwright 自动登录获取 Token 并缓存"""
    print('[jinying] 自动登录获取Token...')
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f'{BASE_URL}/user/login', wait_until='networkidle', timeout=30000)
            # 账号密码从环境变量读取（部署时设置，避免硬编码）
            jy_user = os.environ.get("JINYING_USER", "your-username")
            jy_pass = os.environ.get("JINYING_PASSWORD", "your-password")
            page.fill('input[type="text"], input[placeholder*="账号"], input:first-of-type', jy_user)
            page.fill('input[type="password"]', jy_pass)
            page.click('button')
            page.wait_for_url('**/workplace**', timeout=15000)
            token_str = page.evaluate("localStorage.getItem('pro__Access-Token')")
            browser.close()
            if token_str:
                import json as _json
                cache = _json.loads(token_str)
                os.makedirs(os.path.dirname(TOKEN_CACHE_LOCAL), exist_ok=True)
                with open(TOKEN_CACHE_LOCAL, 'w', encoding='utf-8') as f:
                    _json.dump(cache, f, ensure_ascii=False)
                print(f'[jinying] Token自动获取成功，有效期至 {datetime.fromtimestamp(cache["expire"]/1000).strftime("%Y-%m-%d %H:%M")}')
            else:
                raise Exception('登录后未获取到Token')
    except Exception as e:
        raise Exception(f'自动登录失败: {e}\n请手动在浏览器登录 http://safety.jinying.com:18181 后重试')


def _load_token():
    token_file = _get_token_path()
    with open(token_file, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    expire = cache.get('expire', 0)
    if expire < time.time() * 1000:
        # Token 过期，自动刷新
        print('[jinying] Token已过期，尝试自动刷新...')
        _auto_login_refresh()
        with open(token_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        if cache.get('expire', 0) < time.time() * 1000:
            raise Exception('Token刷新后仍然过期，请手动登录')
    return cache['value']


def _headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }


# ── API ──

def _get(token, path, params=None):
    url = f'{BASE_URL}{path}'
    resp = requests.get(url, params=params, headers=_headers(token), timeout=60)
    resp.raise_for_status()
    return resp.json()


def _fetch_all(token, path, params_template, name):
    """分页拉取全部数据"""
    params = dict(params_template)
    all_rows = []
    page = 1

    while True:
        params['pageNo'] = page
        params['pageSize'] = 500
        r = _get(token, path, params)
        if not r.get('success'):
            raise Exception(f'{name} API失败: code={r.get("code")} msg={r.get("message")}')

        data = r.get('data', {})
        rows = data.get('rows', [])
        total = data.get('totalRows', 0)
        all_rows.extend(rows)
        print(f'  [{name}] 第{page}页 {len(rows)}条 (累计{len(all_rows)}/{total})')

        if len(all_rows) >= total or not rows:
            break
        page += 1

    return all_rows


# ── 字段清理 ──

# 安全履职计划
_PLAN_MAP = {
    'typeDescription': '计划类型',
    'planStatus': '计划状态',
    'startTime': '开始时间',
    'endTime': '结束时间',
    'userName': '责任人',
    'orgName': '责任单位',
    'posName': '岗位名称',
    'performanceIndicators': '计划内容',
    'completionMethod': '完成方式',
    'lastCompletionTime': '最近完成时间',
    'lastCompletionStatus': '最近完成状态',
    'intervalPeriod': '间隔周期(天)',
    'createTime': '创建时间',
}
_PLAN_INTERNAL = {'id', 'createUser', 'updateTime', 'updateUser', 'configId',
                  'usedOrgId', 'userId', 'planResults', 'feedTime', 'fileId',
                  'planStatusList', 'inspectionConclusion', 'fileIdsStr', 'orgIds',
                  'filesNameStr', 'modelFileId', 'isJT', 'reportContent', 'days',
                  'filesObjectStr', 'planFileConfigs', 'fileExtension', 'fileList',
                  'lastStatus', 'planType', 'fileId', 'appStatus', 'posId'}

# 隐患治理
_RISK_MAP = {
    'orgName': '隐患项目',
    'riskName': '隐患类别',
    'riskLevel': '隐患级别',
    'responsibleUserName': '整改负责人',
    'rectificationTime': '整改期限',
    'riskDescript': '隐患描述',
    'rectificationMeasure': '整改措施',
    'checkStatus': '审核状态',
    'riskStatus': '隐患状态',
    'completionTime': '完成时间',
    'createUserName': '创建人',
    'createTime': '创建时间',
    'delayDay': '延期天数',
    'delayRemark': '延期说明',
    'remainingDays': '剩余天数',
    'delayStatus': '延期状态',
    'address': '发生地点',
    'disposeUserName': '整改执行人',
    'checkUserName': '验收人',
    'checkTime': '验收时间',
}
_RISK_INTERNAL = {'id', 'orgId', 'inspectType', 'responsibleUser',
                  'responsibleUserAccount', 'riskPhoto', 'riskPhotoPath',
                  'recordId', 'rectificationPhoto', 'rectificationPhotoPath',
                  'checkDescript', 'delayStatus', 'createUser', 'createUserAccount',
                  'updateTime', 'updateUser', 'recordCreateTime', 'delayFlag', 'sort',
                  'riskNameId', 'riskPhoto', 'rectificationPhoto'}

# 消防水监测（数据监测中心 - 消防水监测，API: /api/device/data/water/page）
_FIRE_MAP = {
    'orgName': '所属项目',
    'deviceName': '设备名称',
    'imei': '设备编号',
    'devicePosition': '安装位置',
    'realtimeValue': '实时水压',
    'temperature': '温度',
    'isOnline': '在线状态',
    'isNormal': '正常状态',
    'networkSignal': '网络信号',
    'detectorBattery': '探测器电量',
    'moduleBattery': '模块电量',
    'reportTime': '上报时间',
    'waterDeviceType': '设备类型',
    'deviceModel': '设备型号',
}
_FIRE_INTERNAL = {'id', 'deviceId', 'posId', 'orgId', 'createUser', 'updateUser',
                  'updateTime', 'createTime', 'waterDeviceType', 'deviceModel',
                  'sysType', 'proType', 'deviceType'}


_FIRE_SYS_TYPE = {1: '火灾自动报警', 2: '消防联动控制', 3: '消火栓', 4: '自动喷淋',
                   5: '气体灭火', 6: '泡沫灭火', 7: '干粉灭火', 8: '防排烟',
                   9: '应急照明', 10: '防火分隔', 11: '消防广播', 12: '消防水监测'}

_FIRE_COMP_TYPE = {1: '探测器', 2: '模块', 3: '手动报警', 4: '消火栓按钮',
                    5: '水流指示', 6: '压力开关', 7: '楼层显示', 8: '主机设备'}


def _clean(raw_list, field_map, internal_set):
    """字段清理：重命名+过滤内部字段"""
    cleaned = []
    for row in raw_list:
        item = {}
        for k, v in row.items():
            if k in internal_set:
                continue
            if k in field_map:
                item[field_map[k]] = v if v is not None else ''
            elif v is not None and str(v).strip() not in ('', 'null', 'None'):
                item[k] = v
        if item:
            cleaned.append(item)
    return cleaned


# ── 状态值中文映射（来源：后端字典API /api/sysDictType/tree） ──

def _plan_status(v):
    """安全计划状态：1=已开始, 2=已完成, 3=已逾期, 4=逾期完成, 5=报备中, 6=已关闭"""
    m = {'1': '已开始', '2': '已完成', '3': '已逾期', '4': '逾期完成',
         '5': '报备中', '6': '已关闭'}
    return m.get(str(v), str(v) if v is not None else '')


def _risk_level(v):
    """隐患级别：1=一般隐患, 2=较大隐患, 3=重大隐患"""
    m = {'1': '一般隐患', '2': '较大隐患', '3': '重大隐患'}
    return m.get(str(v), str(v) if v is not None else '')


def _risk_status(v):
    """隐患状态：1=整改中, 2=已整改, 3=未整改, 4=待核查, 5=待延期, 6=逾期整改, 7=待提交"""
    m = {
        '1': '整改中', '2': '已整改', '3': '未整改',
        '4': '待核查', '5': '待延期', '6': '逾期整改', '7': '待提交',
    }
    return m.get(str(v), str(v) if v is not None else '')


def _check_status(v):
    """核查状态：1=已整改完成, 2=未整改完成"""
    m = {'1': '已整改完成', '2': '未整改完成'}
    return m.get(str(v), str(v) if v is not None else '')


def _check_status(v):
    m = {'0': '待审核', '1': '已通过', '2': '已驳回'}
    return m.get(str(v), str(v) if v is not None else '')


# ── 计算剩余天数（remainingDays 是前端计算字段，API返回null） ──
def _calc_remaining_days(records):
    """对隐患记录，根据整改期限+延期天数计算剩余天数"""
    from datetime import date, timedelta
    today = date.today()
    for r in records:
        deadline = r.get('整改期限')
        if deadline:
            try:
                d = date.fromisoformat(str(deadline)[:10])
                delay = r.get('延期天数')
                if delay and str(delay).strip() not in ('', 'None', 'null'):
                    d = d + timedelta(days=int(delay))
                r['剩余天数'] = (d - today).days
            except:
                r['剩余天数'] = None
        else:
            r['剩余天数'] = None
    return records


def _map_status(records, status_fields):
    """对状态字段做中文映射"""
    mappers = {
        '计划状态': _plan_status,
        '隐患级别': _risk_level,
        '隐患状态': _risk_status,
        '审核状态': _check_status,
        '在线状态': lambda v: '在线' if v == 1 or v is True or str(v) == '1' else '离线' if v == 0 or v is False or str(v) == '0' else str(v),
        '正常状态': lambda v: '正常' if v == 1 or v is True or str(v) == '1' else '异常' if v == 0 or v is False or str(v) == '0' else str(v),
    }
    result = []
    for r in records:
        nr = dict(r)
        for f, fn in mappers.items():
            if f in r and r[f] is not None:
                nr[f] = fn(r[f])
        result.append(nr)
    return result


# ── 输出文件 ──

PLAN_FILE = os.path.join(CACHE_DIR, 'plan_records.json')
RISK_FILE = os.path.join(CACHE_DIR, 'risk_records.json')
FIRE_FILE = os.path.join(CACHE_DIR, 'fire_records.json')
LOG_FILE = os.path.join(DATA_DIR, 'jinying_update_log.json')


# ── 主爬取逻辑 ──

def _date_range(days: int) -> tuple:
    """返回 (start, end) 日期字符串，默认向前取 days 天"""
    from datetime import timedelta
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def sync_all() -> dict:
    """爬取全部三个数据源（全量拉取）"""
    t0 = time.time()

    log_entry = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'running',
        'plan_count': 0,
        'risk_count': 0,
        'fire_count': 0,
    }

    try:
        token = _load_token()
        print(f'[jinying] Token加载成功')

        # 安全履职计划（2026全年）
        print(f'[jinying] 正在拉取安全履职计划（2026年）...')
        plan_raw = _fetch_all(token, '/api/planOwn/search', {
            'startTime': '2026-01-01',
            'endTime': '2026-12-31',
        }, '安全履职')
        plan_clean = _map_status(_clean(plan_raw, _PLAN_MAP, _PLAN_INTERNAL), _PLAN_MAP)
        with open(PLAN_FILE, 'w', encoding='utf-8') as f:
            json.dump(plan_clean, f, ensure_ascii=False, indent=2)
        log_entry['plan_count'] = len(plan_clean)
        print(f'[jinying] 安全履职: {len(plan_clean)} 条')

        # 隐患治理（2026全年）
        print(f'[jinying] 正在拉取隐患治理（2026年）...')
        risk_raw = _fetch_all(token, '/api/allRisk/page', {
            'rectificationTimeStart': '2026-01-01',
            'rectificationTimeEnd': '2026-12-31',
        }, '隐患治理')
        risk_clean = _calc_remaining_days(
            _map_status(_clean(risk_raw, _RISK_MAP, _RISK_INTERNAL), _RISK_MAP)
        )
        with open(RISK_FILE, 'w', encoding='utf-8') as f:
            json.dump(risk_clean, f, ensure_ascii=False, indent=2)
        log_entry['risk_count'] = len(risk_clean)
        print(f'[jinying] 隐患治理: {len(risk_clean)} 条')

        # 消防水监测
        print(f'[jinying] 正在拉取消防水监测...')
        fire_raw = _fetch_all(token, '/api/device/data/water/page', {}, '消防水监测')
        fire_clean = _map_status(_clean(fire_raw, _FIRE_MAP, _FIRE_INTERNAL), _FIRE_MAP)
        with open(FIRE_FILE, 'w', encoding='utf-8') as f:
            json.dump(fire_clean, f, ensure_ascii=False, indent=2)
        log_entry['fire_count'] = len(fire_clean)
        print(f'[jinying] 消防水监测: {len(fire_clean)} 条')

        log_entry['status'] = 'success'
        log_entry['finished'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        duration = time.time() - t0
        log_entry['duration'] = f'{duration:.1f}s'
        total = len(plan_clean) + len(risk_clean) + len(fire_clean)
        print(f'[jinying] 完成! 共 {total} 条, 耗时{duration:.1f}s')

    except Exception as e:
        log_entry['status'] = 'error'
        log_entry['message'] = str(e)
        log_entry['finished'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'[jinying] 错误: {e}')
        raise

    finally:
        _save_log(log_entry)

    return log_entry


# ── 日志 ──

def _save_log(entry):
    logs = _load_log()
    logs.insert(0, entry)
    logs = logs[:100]
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def _load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


# ── 数据读取 ──

def load_plan() -> list:
    if os.path.exists(PLAN_FILE):
        with open(PLAN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def load_risk() -> list:
    if os.path.exists(RISK_FILE):
        with open(RISK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def load_fire() -> list:
    if os.path.exists(FIRE_FILE):
        with open(FIRE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def get_last_update() -> str:
    logs = _load_log()
    for entry in logs:
        if entry.get('status') == 'success':
            return entry.get('finished', entry.get('time', ''))
    return ''


def get_counts() -> dict:
    """获取缓存中的数据条数"""
    return {
        'plan': len(load_plan()),
        'risk': len(load_risk()),
        'fire': len(load_fire()),
    }


def get_plan_count() -> int:
    return len(load_plan())


def get_risk_count() -> int:
    return len(load_risk())


def get_fire_count() -> int:
    return len(load_fire())
