"""
123物联网平台 - MQTT实时数据监听模块
集成到集控中心，后台持续运行，实时接收设备传感器数据

MQTT协议:
- 服务器: wss://comm.sd123iot.com:443/mqtt
- 用户名: 账号名
- 密码: t:{token}
- 订阅Topic: /app/data/{devId}/u (数据上传)
-           /app/status/{devId}/u (状态变更)
- 消息格式: JSON {dataPoints: [{variableName, value, time}]}
"""
import requests
import hashlib
import json
import time
import threading
import os
import urllib3
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

urllib3.disable_warnings()

BASE_URL = 'https://cloud.sd123iot.com:8443/usrCloud'
MQTT_SERVER = 'comm.sd123iot.com'
MQTT_PORT = 443
MQTT_PATH = '/mqtt'

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_DIR, 'data')
REALTIME_FILE = os.path.join(DATA_DIR, 'sd123_realtime.json')
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'sd123_accounts.xlsx')

# 全局状态
_lock = threading.Lock()
_device_info = {}   # {devid: {name, template, project, group, address, ...}}
_realtime_data = {} # {devid: {温度: 25.3, 湿度: 60, 水浸状态: 0, 最后更新: ...}}
_mqtt_clients = []
_msg_count = 0
_running = False
_last_save = 0


# ── 工具函数 ──

def _md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def _login(account, password):
    try:
        r = requests.post(f'{BASE_URL}/user/login',
            json={'account': account, 'password': _md5(password)},
            verify=False, timeout=15)
        data = r.json()
        if data.get('status') == 0:
            return data['data']['token']
    except Exception as e:
        print(f'[sd123-mqtt] 登录失败 {account}: {e}')
    return None


def _get_all_devices(token):
    headers = {'Content-Type': 'application/json', 'token': token}
    all_devs = []
    page = 1
    while True:
        try:
            r = requests.post(f'{BASE_URL}/dev/getDevs', headers=headers,
                json={'pageNo': page, 'pageSize': 500}, verify=False, timeout=30)
            data = r.json()
            if data.get('status') != 0:
                break
            devs = data['data'].get('dev', [])
            all_devs.extend(devs)
            if len(all_devs) >= data['data'].get('total', 0) or not devs:
                break
            page += 1
        except Exception as e:
            print(f'[sd123-mqtt] 获取设备失败: {e}')
            break
    return all_devs


def _load_accounts():
    """读取账号表 -> [(项目名, 账号, 密码), ...]"""
    try:
        import openpyxl
        if not os.path.exists(ACCOUNTS_FILE):
            return []
        wb = openpyxl.load_workbook(ACCOUNTS_FILE, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        wb.close()
        accounts = []
        for row in rows:
            if len(row) >= 3 and row[1] and row[2]:
                project = str(row[1]).strip()
                account = str(row[2]).strip()
                password = str(row[3]).strip() if len(row) > 3 else ''
                accounts.append((project, account, password))
        return accounts
    except Exception as e:
        print(f'[sd123-mqtt] 读取账号失败: {e}')
        return []


def _save_realtime():
    """保存实时数据到文件"""
    global _last_save
    with _lock:
        if not _realtime_data:
            return
        payload = {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'device_count': len(_realtime_data),
            'msg_count': _msg_count,
            'devices': {}
        }
        for devid, data in _realtime_data.items():
            info = _device_info.get(devid, {})
            payload['devices'][devid] = {
                '归属项目': info.get('projectName', ''),
                '设备名称': info.get('name', ''),
                '设备类型': info.get('templateName', ''),
                '设备分组': info.get('groupName', ''),
                '地址': info.get('address', ''),
                **data
            }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REALTIME_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _last_save = time.time()


# ── MQTT 回调 ──

def _on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        account = userdata.get('account', '?')
        device_ids = userdata.get('device_ids', [])
        print(f'[sd123-mqtt] 已连接: {account}')
        for devid in device_ids:
            # 订阅数据上传和状态变更
            client.subscribe(f'/app/data/{devid}/u')
            client.subscribe(f'/app/status/{devid}/u')
        print(f'[sd123-mqtt] 已订阅 {len(device_ids)} 台设备')
    else:
        print(f'[sd123-mqtt] 连接失败: rc={rc}')


def _on_message(client, userdata, msg):
    global _msg_count
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode('utf-8'))

        if '/app/data/' in topic:
            devid = payload.get('deviceId', '')
            if not devid:
                parts = topic.split('/')
                if len(parts) >= 4:
                    devid = parts[3]

            if devid:
                with _lock:
                    if devid not in _realtime_data:
                        _realtime_data[devid] = {}

                    for dp in payload.get('dataPoints', []):
                        name = dp.get('variableName', dp.get('name', ''))
                        value = dp.get('value')
                        if name:
                            _realtime_data[devid][name] = value

                    _realtime_data[devid]['最后更新时间'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    _msg_count += 1

                # 打印数据
                info = _device_info.get(devid, {})
                name = info.get('name', devid)
                values = [f"{dp.get('variableName','?')}={dp.get('value','?')}" for dp in payload.get('dataPoints', [])]
                print(f'[sd123-data] {name}: {", ".join(values[:4])}')

        elif '/app/status/' in topic:
            devid = payload.get('deviceId', '')
            status = payload.get('status', '')
            if devid:
                with _lock:
                    if devid not in _realtime_data:
                        _realtime_data[devid] = {}
                    _realtime_data[devid]['在线状态'] = '在线' if status == 1 else '离线'

    except Exception as e:
        print(f'[sd123-mqtt] 消息处理异常: {e}')


def _on_disconnect(client, userdata, rc):
    print(f'[sd123-mqtt] 连接断开: rc={rc}')


def _mqtt_loop(token, account, password, project, device_ids):
    """单个账号的MQTT监听循环（带自动重连+Token刷新）"""
    current_token = token
    while _running:
        try:
            client_id = f'APP:{int(time.time()*1000)}:{account[:8]}'
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                transport='websockets',
                protocol=mqtt.MQTTv311
            )
            client.tls_set()
            client.username_pw_set(account, f't:{current_token}')
            client.user_data_set({'account': account, 'device_ids': device_ids})
            client.on_connect = _on_connect
            client.on_message = _on_message
            client.on_disconnect = _on_disconnect
            client.connect(MQTT_SERVER, MQTT_PORT, keepalive=600)
            _mqtt_clients.append(client)
            client.loop_forever()
        except Exception as e:
            print(f'[sd123-mqtt] 连接异常 {account}: {e}')

        if _running:
            # 重新登录刷新Token
            new_token = _login(account, password)
            if new_token:
                current_token = new_token
                print(f'[sd123-mqtt] Token已刷新: {account}')
            else:
                print(f'[sd123-mqtt] Token刷新失败: {account}, 60秒后重试')
                time.sleep(50)
            time.sleep(10)


def _save_loop():
    """定时保存循环"""
    while _running:
        time.sleep(60)
        _save_realtime()


# ── 对外接口 ──

def start():
    """启动MQTT监听（后台线程）"""
    global _running
    if not HAS_MQTT:
        print('[sd123-mqtt] paho-mqtt 未安装，跳过MQTT监听')
        return False

    if _running:
        print('[sd123-mqtt] 已在运行中')
        return True

    _running = True

    # 读取账号
    accounts = _load_accounts()
    if not accounts:
        print('[sd123-mqtt] 无账号配置')
        _running = False
        return False

    print(f'[sd123-mqtt] 读取到 {len(accounts)} 个账号')

    # 登录并收集设备
    all_tokens = []
    all_device_ids = set()

    for project, account, password in accounts:
        token = _login(account, password)
        if not token:
            print(f'[sd123-mqtt] 登录失败: {project} ({account})')
            continue

        devices = _get_all_devices(token)
        print(f'[sd123-mqtt] {project}: {len(devices)} 台设备')

        all_tokens.append({'token': token, 'account': account, 'password': password, 'project': project})

        for dev in devices:
            devid = dev['devid']
            _device_info[devid] = {
                'name': dev.get('name', ''),
                'templateName': dev.get('templateName', ''),
                'projectName': project,
                'groupName': dev.get('groupName', ''),
                'address': dev.get('address', ''),
                'onlineStatus': dev.get('onlineStatus', 0),
            }
            all_device_ids.add(devid)

    all_device_ids = list(all_device_ids)
    print(f'[sd123-mqtt] 总计 {len(all_device_ids)} 台设备')

    # 启动MQTT线程（每个账号一个连接）
    for t in all_tokens:
        thread = threading.Thread(
            target=_mqtt_loop,
            args=(t['token'], t['account'], t['password'], t['project'], all_device_ids),
            daemon=True
        )
        thread.start()
        time.sleep(0.3)

    # 启动定时保存线程
    save_thread = threading.Thread(target=_save_loop, daemon=True)
    save_thread.start()

    print(f'[sd123-mqtt] MQTT监听已启动，等待数据推送...')
    return True


def stop():
    """停止MQTT监听"""
    global _running
    _running = False
    for c in _mqtt_clients:
        try:
            c.disconnect()
        except:
            pass
    _mqtt_clients.clear()
    _save_realtime()
    print('[sd123-mqtt] 已停止')


def get_realtime():
    """获取实时数据（供API调用）"""
    with _lock:
        if not _realtime_data:
            # 尝试从文件加载
            if os.path.exists(REALTIME_FILE):
                try:
                    with open(REALTIME_FILE, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
            return {'updated_at': '', 'device_count': 0, 'msg_count': 0, 'devices': {}}

        devices = {}
        for devid, data in _realtime_data.items():
            info = _device_info.get(devid, {})
            devices[devid] = {
                '归属项目': info.get('projectName', ''),
                '设备名称': info.get('name', ''),
                '设备类型': info.get('templateName', ''),
                '设备分组': info.get('groupName', ''),
                '地址': info.get('address', ''),
                **data
            }

        return {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'device_count': len(devices),
            'msg_count': _msg_count,
            'devices': devices
        }


def get_status():
    """获取MQTT监听状态"""
    return {
        'running': _running,
        'device_count': len(_device_info),
        'data_count': len(_realtime_data),
        'msg_count': _msg_count,
        'mqtt_clients': len(_mqtt_clients),
    }
