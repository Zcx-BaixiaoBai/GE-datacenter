"""
泛微OA预算执行情况表爬虫
流程: Playwright登录 -> guid -> tempData -> implementationReport -> table/datas (分页)
"""
import asyncio
import json
import os
from datetime import datetime

_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(_DIR, "data")
REPORT1_FILE = os.path.join(DATA_DIR, "budget_report1.json")
REPORT2_FILE = os.path.join(DATA_DIR, "budget_report2.json")
LOG_FILE = os.path.join(DATA_DIR, "budget_update_log.json")

CONFIG = {
    "username": "",
    "password": "",
    "login_url": "",
}
# 从同级 config.json 读取（config.json 含真实凭证，已在 .gitignore 中排除）
_cfg_path = os.path.join(_DIR, "config.json")
if os.path.exists(_cfg_path):
    try:
        with open(_cfg_path, "r", encoding="utf-8") as _f:
            _loaded = json.load(_f)
        CONFIG.update(_loaded.get("budget", {}))
    except Exception:
        pass

# 两个表单的筛选条件
REPORTS = [
    {
        "name": "经营类预算",
        "file": REPORT1_FILE,
        "form_data": "orgType=18004&fnayear=2026&subjectType=1&orgId=2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024,2025,2026,2027,2028,2029,2030,2031,2032,2033,2034,3001,4001,11501,12001,13501,14001,15001,15002,15003,15004,15005,15007,15008,15009,15010,15011,15501&subjectIds=15578,15579,15581,15582,15585,15586,15587&monthPeriod=1,2,3,4,5,6,7,8,9,10,11,12&quarterPeriod=&halfYearPeriod=&allYearPeriod=&sumSubOrg=&subCompanyPath=0&orderType=0&departmentPath=0&rptViewType=0&qryFunctionType=1",
    },
    {
        "name": "物业类预算",
        "file": REPORT2_FILE,
        "form_data": "orgType=18004&fnayear=2026&subjectType=1&orgId=501,502,503,504,505,506,507,508,509,510,511,512,513,514,515,516,517,518,519,520,521,522,523,524,525,526,527,528,529,530,1001,2501,3501,4501,5001,5501,6001,6501,6502,7501,8001,8501,9001,9501,10001,10501,10502,11001,12501,13001,14501,16001,16002&subjectIds=1059,2542,3042,3043,3541,3542,3543&monthPeriod=1,2,3,4,5,6,7,8,9,10,11,12&quarterPeriod=&halfYearPeriod=&allYearPeriod=&sumSubOrg=&subCompanyPath=0&orderType=0&departmentPath=0&rptViewType=0&qryFunctionType=1",
    },
]

# 浏览器内执行的JS：拉取单个表单全量数据
CRAWL_JS = """
async (formData) => {
    const base = 'http://ecbpm.jinying.com:8090';
    const formH = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': base + '/wui/index.html',
    };
    const jsonH = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        'X-Requested-With': 'XMLHttpRequest',
    };
    const body = formData;

    // Step 1: GUID
    const rGuid = await fetch(base + '/api/fna/reportBase/guid?__random__=' + Date.now(), {
        credentials: 'include'
    });
    const jGuid = await rGuid.json();
    const guid = jGuid.guid;

    // Step 2: tempData
    const tempBody = body + '&_guid1=' + encodeURIComponent(guid) + '&';
    const r1 = await fetch(base + '/api/fna/tempData/implementation', {
        method: 'POST', headers: formH, body: tempBody, credentials: 'include'
    });
    const j1 = await r1.json();

    // Step 3: implementationReport
    const r2 = await fetch(base + '/api/fna/report/implementationReport', {
        method: 'POST', headers: formH, body: tempBody, credentials: 'include'
    });
    const j2 = await r2.json();

    if (j2.flag !== 'success' || !j2.datas) {
        return JSON.stringify({error: 'report failed', report: j2});
    }

    const dataKey = j2.datas;

    // Step 4: count
    const countBody = 'dataKey=' + encodeURIComponent(dataKey);
    const rCount = await fetch(base + '/api/ec/dev/table/counts', {
        method: 'POST', headers: jsonH, body: countBody, credentials: 'include'
    });
    const jCount = await rCount.json();
    const total = jCount.count || 0;

    // Step 5: paginate all data
    const allRows = [];
    const pageSize = 10;
    const totalPages = Math.ceil(total / pageSize);

    for (let pg = 1; pg <= totalPages; pg++) {
        const pgBody = 'dataKey=' + encodeURIComponent(dataKey) + '&current=' + pg + '&sortParams=' + encodeURIComponent('[]');
        const rPg = await fetch(base + '/api/ec/dev/table/datas', {
            method: 'POST', headers: jsonH, body: pgBody, credentials: 'include'
        });
        const jPg = await rPg.json();
        if (jPg.datas && jPg.datas.length > 0) {
            allRows.push(...jPg.datas);
        }
    }

    return JSON.stringify({
        guid: guid,
        dataKey: dataKey,
        total: total,
        fetched: allRows.length,
        data: allRows,
    });
}
"""


def save_update_log(entry: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    logs.insert(0, entry)
    logs = logs[:50]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def load_update_log() -> list:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_report(report_type: int) -> list:
    """Load report data. report_type: 1=business, 2=property"""
    filepath = REPORT1_FILE if report_type == 1 else REPORT2_FILE
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── 字段清理 ──

# 输出字段：原始key -> 中文名
_FIELD_MAP = {
    "orgIdspan": "预算单位",
    "qspan": "预算期间",
    "subjectIdspan": "预算科目",
    "budgetAmtspan": "年初预算数",
    "budgetAmt1span": "调整后预算数",
    "budgetAmt2span": "追加后预算数",
    "actualAmtspan": "实际发生数",
    "approvalAmtspan": "审批中费用",
    "changeAmtspan": "预算追加数",
    "availableAmtspan": "可用预算数",
    "execRatiospan": "执行占比",
}

# 需要丢弃的内部字段
_INTERNAL = {"id", "orgId", "subjectId", "q", "budgetAmt", "budgetAmt1",
             "budgetAmt2", "actualAmt", "approvalAmt", "changeAmt",
             "availableAmt", "execRatio", "guid1", "guid1span",
             "randomFieldId", "randomFieldIdspan", "idspan"}


def _clean_records(raw_list: list) -> list:
    """清理原始数据：丢弃内部字段，key转中文"""
    cleaned = []
    for row in raw_list:
        item = {}
        for k, v in row.items():
            if k in _INTERNAL:
                continue
            if k in _FIELD_MAP:
                item[_FIELD_MAP[k]] = v
        if item:
            cleaned.append(item)
    return cleaned


def get_last_update() -> str:
    logs = load_update_log()
    for entry in logs:
        if entry.get("status") == "success":
            return entry.get("finished", entry.get("time", ""))
    return ""


async def crawl_all_async():
    """Async version — for standalone use / manual testing"""
    from playwright.async_api import async_playwright

    log_entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "running", "message": "Crawling..."}
    save_update_log(log_entry)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            print("[budget] Logging in to OA...")
            await page.goto(CONFIG["login_url"], wait_until="networkidle", timeout=30000)
            await page.fill('input[type="text"]', CONFIG["username"])
            await page.fill('input[type="password"]', CONFIG["password"])
            login_ok = False
            for attempt in range(3):
                try:
                    btn = page.get_by_role("button", name="登 录", exact=True)
                    await btn.click()
                    try: await page.wait_for_url("**/index.html**", timeout=8000)
                    except: pass
                    await page.wait_for_timeout(2000)
                    if "login" not in page.url.lower() and await page.locator('input[type="password"]').count() == 0:
                        login_ok = True; break
                    print(f"[budget] 登录尝试 {attempt+1} 似乎未成功, 重试...")
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[budget] 登录尝试 {attempt+1} 失败: {e}")
                    await page.wait_for_timeout(3000)
            if not login_ok: raise RuntimeError("登录失败，3次尝试均未成功")
            print(f"[budget] Logged in, URL: {page.url}")
            report_url = "http://ecbpm.jinying.com:8090/wui/index.html#/main/report/fna/implementation?menuIds=110,10174&menuPathIds=110,205,10174"
            await page.goto(report_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            for report in REPORTS:
                print(f"[budget] Crawling {report['name']}...")
                result = await page.evaluate(CRAWL_JS, report["form_data"])
                parsed = json.loads(result)
                if "error" in parsed: print(f"[budget] ERROR: {parsed['error']}"); continue
                data = parsed.get("data", [])
                data = _clean_records(data)
                print(f"[budget] {report['name']}: {len(data)} rows")
                with open(report["file"], "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            await browser.close()
        log_entry.update(status="success", message="Data updated", finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        save_update_log(log_entry); print("[budget] Done!")
    except Exception as e:
        log_entry.update(status="error", message=str(e), finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        save_update_log(log_entry); print(f"[budget] ERROR: {e}"); raise


def crawl_all():
    """Sync version — for scheduler/threaded use (no asyncio.run)"""
    from playwright.sync_api import sync_playwright

    log_entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "running", "message": "Crawling..."}
    save_update_log(log_entry)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            print("[budget] Logging in to OA...")
            page.goto(CONFIG["login_url"], wait_until="networkidle", timeout=30000)
            page.fill('input[type="text"]', CONFIG["username"])
            page.fill('input[type="password"]', CONFIG["password"])
            login_ok = False
            for attempt in range(3):
                try:
                    btn = page.get_by_role("button", name="登 录", exact=True)
                    btn.click()
                    try: page.wait_for_url("**/index.html**", timeout=8000)
                    except: pass
                    page.wait_for_timeout(2000)
                    if "login" not in page.url.lower() and page.locator('input[type="password"]').count() == 0:
                        login_ok = True; break
                    print(f"[budget] 登录尝试 {attempt+1} 似乎未成功, 重试...")
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[budget] 登录尝试 {attempt+1} 失败: {e}")
                    page.wait_for_timeout(3000)
            if not login_ok: raise RuntimeError("登录失败，3次尝试均未成功")
            print(f"[budget] Logged in, URL: {page.url}")
            report_url = "http://ecbpm.jinying.com:8090/wui/index.html#/main/report/fna/implementation?menuIds=110,10174&menuPathIds=110,205,10174"
            page.goto(report_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            for report in REPORTS:
                print(f"[budget] Crawling {report['name']}...")
                result = page.evaluate(CRAWL_JS, report["form_data"])
                parsed = json.loads(result)
                if "error" in parsed: print(f"[budget] ERROR: {parsed['error']}"); continue
                data = parsed.get("data", [])
                data = _clean_records(data)
                print(f"[budget] {report['name']}: {len(data)} rows")
                with open(report["file"], "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            browser.close()
        log_entry.update(status="success", message="Data updated", finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        save_update_log(log_entry); print("[budget] Done!")
    except Exception as e:
        log_entry.update(status="error", message=str(e), finished=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        save_update_log(log_entry); print(f"[budget] ERROR: {e}"); raise
