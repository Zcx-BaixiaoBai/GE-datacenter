"""
瑞信系统爬虫 -- 全自动版
自动取Token（RSA加密登录），自动缓存，自动刷新
"""
import requests
import json
import os
import base64
from datetime import datetime, timedelta
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# RSA公钥（从前端JS提取）
_PUB_KEY_B64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDBX6ofbahoCvHPv7GNORBfghGbyGExwqJaHHc6BzbDj5vUz94DNKHRggqiBnpW43ks/47kZP1i0Yk1ar1lSZUZTr4POgoHM3s8UfxnQ/0190lmonMeULAHjH+tV3ry+rVMJTKpQdiSMpMvK070rP6iD3z7QWcNMYOpZtLVUE5c1QIDAQAB"
_PEM_DATA = "-----BEGIN PUBLIC KEY-----\n" + _PUB_KEY_B64 + "\n-----END PUBLIC KEY-----"
_RSA_KEY = RSA.import_key(_PEM_DATA)

_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(_DIR, "data")
TOKEN_CACHE = os.path.join(DATA_DIR, "ruixin_token.json")
CACHE_FILE = os.path.join(DATA_DIR, "ruixin_cache.json")


# ── 字段映射 ──
_FIELD_MAP = {
    "areaid": "区域ID", "areaname": "区域",
    "buildingid": "楼栋ID", "buildingname": "楼栋",
    "floorid": "楼层ID", "floorname": "楼层",
    "deivceid": "设备ID", "overtime": "超时时间",
    "roomid": "房间ID", "roomname": "房间",
    "unitname": "单元", "wallet": "账户余额",
    "basewallet": "基础余额", "subsidywallet": "补贴余额",
    "splitsubsidywallet": "分摊补助余额", "subsidyelectricwallet": "电费补助",
    "subsidycoldwaterwallet": "冷水补助", "subsidyhotwaterwallet": "热水补助",
    "subsidyheatingwallet": "取暖补助", "identityname": "身份",
    "producttype": "产品分类", "productname": "仪表类型",
    "commstatus": "通讯状态", "devicestatus": "设备状态",
    "address": "安装地址", "switchstatus": "开关状态",
    "switchstatusorg": "开关状态编码", "tunnelname": "通道名称",
    "tunnel": "通道", "tunnelnum": "通道号",
    "display": "显示值", "devicedisplay": "表读数",
    "gatewaynum": "网关号", "channelnum": "通道号",
    "productsign": "产品标识", "productid": "产品ID",
    "commtime": "通讯时间", "time": "数据时间",
    "controllable": "可控", "writeable": "可写",
    "atomcode": "原子编码", "controlmode": "控制模式",
    "pricecalctype": "计价方式", "balancestatus": "余额状态",
    "status": "状态", "warningenable": "告警启用",
    "warningthreshold": "告警阈值", "isanyone": "是否有人",
    "location": "位置", "combinecmdenabled": "合控命令启用",
    "commtype": "通讯类型", "csq": "信号强度",
    "batterystatus": "电池状态", "ct": "CT变比",
    "pt": "PT变比", "devicenum": "仪表编号",
    "meterversion": "表版本", "businessformat": "业务格式",
}

# 不丢弃任何字段，全部导出（与原服务一致）
_INTERNAL = set()


def _clean_records(records: list) -> list:
    """清理原始记录：丢弃内部字段，key转中文"""
    cleaned = []
    for row in records:
        item = {}
        for k, v in row.items():
            if k in _INTERNAL:
                continue
            if k in _FIELD_MAP:
                item[_FIELD_MAP[k]] = v
            else:
                item[k] = v  # 未映射的保留原名
        if item:
            cleaned.append(item)
    return cleaned


def encrypt_password(password: str) -> str:
    cipher = PKCS1_v1_5.new(_RSA_KEY)
    encrypted = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def _save_token(token: str, expires_at: str = None):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        "token": token,
        "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires_at or "",
    }
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_token() -> str | None:
    if os.path.exists(TOKEN_CACHE):
        with open(TOKEN_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
            token = data.get("token", "")
            expires_at = data.get("expires_at", "")
            if expires_at:
                try:
                    exp = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() >= exp - timedelta(minutes=5):
                        print("[Token] Token expiring soon, refreshing")
                        return None
                except (ValueError, TypeError):
                    pass
            return token if token else None
    return None


def login(cfg: dict) -> str:
    base_url = cfg.get("base_url", "http://netge.czrxdzonline.cn")
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    if not username or not password:
        raise ValueError("Username/password not configured")

    encrypted_pass = encrypt_password(password)
    url = f"{base_url}/api/basic/users/login"
    payload = {"name": username, "pass": encrypted_pass, "code": "", "uuid": ""}
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    print(f"[login] Logging in as {username}...")
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != 1:
        raise RuntimeError(f"Login failed: {data.get('data', 'unknown')}")

    token = data["data"]["token"]
    expires_at = data["data"].get("exprtime", "")
    _save_token(token, expires_at)
    print(f"[login] OK, expires: {expires_at}")
    return token


def ensure_token(cfg: dict) -> str:
    token = _load_token()
    if not token:
        print("[token] No valid cache, logging in...")
        token = login(cfg)
    return token


def fetch_data(cfg: dict, token: str = None) -> dict:
    if token is None:
        token = ensure_token(cfg)

    base_url = cfg.get("base_url", "http://netge.czrxdzonline.cn")
    url = f"{base_url}/api/prepay/workbench/query"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{base_url}/oprate/index",
    }
    params = {"NeedPaging": "0", "orderby": "sortnum asc"}

    print(f"[fetch] {url}")
    resp = requests.get(url, headers=headers, params=params, timeout=120)

    if resp.status_code == 401:
        print("[fetch] 401, re-login...")
        token = login(cfg)
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, params=params, timeout=120)

    resp.raise_for_status()
    return resp.json()


def extract_records(raw: dict) -> list:
    return raw.get("data", {}).get("list", [])


def cache_data(records: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    cleaned = _clean_records(records)
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(cleaned),
        "records": cleaned,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"[cache] {len(cleaned)} records saved")


def load_cache() -> list:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("records", [])
    return []
