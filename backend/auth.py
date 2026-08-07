"""
金鹰集团数据管理中心 - 认证模块
支持管理员 + 项目用户两级权限
登录时选择项目, 管理员可看全部, 项目用户只能看自己的
"""
import os
import json
import hashlib
import hmac
import time
import base64

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'admin_config.json')

# ⚠️ 部署时务必修改：通过环境变量 AUTH_DEFAULT_PASSWORD / AUTH_SECRET 覆盖默认值
DEFAULT_PASSWORD = os.environ.get("AUTH_DEFAULT_PASSWORD", "admin123")
_SECRET = os.environ.get("AUTH_SECRET", "please-change-this-secret-in-production")


def _encode_project(project):
    """项目名编码为 URL safe 字符串 (HTTP header 兼容)"""
    return base64.urlsafe_b64encode(project.encode('utf-8')).decode('ascii').rstrip('=')


def _decode_project(encoded):
    """解码项目名"""
    try:
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += '=' * padding
        return base64.urlsafe_b64decode(encoded.encode('ascii')).decode('utf-8')
    except:
        return None


def _load_config():
    default = {
        "admin_password_hash": _hash_password(DEFAULT_PASSWORD),
        "project_passwords": {},  # {项目名: 密码hash}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                default.update(saved)
        except:
            pass
    else:
        _save_config(default)
    return default


def _save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _hash_password(pwd):
    return hashlib.sha256(pwd.encode('utf-8')).hexdigest()


def _make_token(pwd_hash, project):
    """生成token: ts.signature.encoded_project"""
    ts = str(int(time.time()))
    encoded_project = _encode_project(project)
    payload = pwd_hash[:16] + ts + project
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{sig}.{encoded_project}"


def _verify_token(token, cfg):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        ts_str, sig, encoded_project = parts
        project = _decode_project(encoded_project)
        if not project:
            return None
        ts = int(ts_str)
        if time.time() - ts > 86400:
            return None

        if project == 'admin':
            pwd_hash = cfg['admin_password_hash']
        else:
            pwd_hash = cfg.get('project_passwords', {}).get(project, '')
            if not pwd_hash:
                return None

        payload = pwd_hash[:16] + ts_str + project
        expected_sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(sig, expected_sig):
            return project
        return None
    except:
        return None


def login(password, project='admin'):
    """验证密码, 返回 {token, project, is_admin} 或 None"""
    cfg = _load_config()

    if project == 'admin':
        if _hash_password(password) == cfg['admin_password_hash']:
            token = _make_token(cfg['admin_password_hash'], 'admin')
            return {'token': token, 'project': 'admin', 'is_admin': True}
        return None

    # 项目用户
    pwd_hash = cfg.get('project_passwords', {}).get(project)
    if pwd_hash and _hash_password(password) == pwd_hash:
        token = _make_token(pwd_hash, project)
        return {'token': token, 'project': project, 'is_admin': False}
    return None


def check_token(token):
    """验证token, 返回项目名或None"""
    if not token:
        return None
    cfg = _load_config()
    return _verify_token(token, cfg)


def get_project_from_token(token):
    """从token提取项目名"""
    if not token:
        return None
    parts = token.split('.')
    if len(parts) == 3:
        return _decode_project(parts[2])
    return None


def is_admin(token):
    """是否管理员"""
    return get_project_from_token(token) == 'admin'


def logout(token):
    pass


def change_password(old_pwd, new_pwd):
    """管理员修改自己的密码"""
    cfg = _load_config()
    if _hash_password(old_pwd) != cfg['admin_password_hash']:
        return False, '旧密码错误'
    cfg['admin_password_hash'] = _hash_password(new_pwd)
    _save_config(cfg)
    return True, '密码修改成功'


def set_project_password(project, password):
    """设置项目密码(管理员操作)"""
    cfg = _load_config()
    if 'project_passwords' not in cfg:
        cfg['project_passwords'] = {}
    cfg['project_passwords'][project] = _hash_password(password)
    _save_config(cfg)
    return True


def get_project_list():
    """获取已配置密码的项目列表"""
    cfg = _load_config()
    return list(cfg.get('project_passwords', {}).keys())


def is_default_password():
    cfg = _load_config()
    return cfg['admin_password_hash'] == _hash_password(DEFAULT_PASSWORD)
