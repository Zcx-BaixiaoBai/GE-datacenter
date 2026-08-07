"""
金鹰集团数据管理中心 - 数据库模块
定义所有集控中心表格对应的 SQLite 表结构
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'center.db')


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ─── 建表 SQL ──────────────────────────────────────────────

SCHEMA_SQL = """

-- ===================== 原始数据表 =====================

-- 瑞信电表原始数据 (ruixin sheet, 63列)
CREATE TABLE IF NOT EXISTS ruixin_meters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq TEXT,              -- A 序号
    region TEXT,           -- B 区域
    building_id TEXT,      -- C 楼栋ID
    building TEXT,         -- D 楼栋
    floor_id TEXT,         -- E 楼层ID
    floor TEXT,            -- F 楼层
    device_id TEXT,        -- G 设备ID
    timeout TEXT,          -- H 超时时间
    room_id TEXT,          -- I 房间ID
    room TEXT,             -- J 房间
    unit TEXT,             -- K 单元
    balance REAL,          -- L 账户余额
    base_balance REAL,     -- M 基础余额
    subsidy_balance REAL,  -- N 补贴余额
    share_balance REAL,    -- O 分摊补助余额
    elec_subsidy REAL,    -- P 电费补助
    cold_water REAL,       -- Q 冷水补助
    hot_water REAL,        -- R 热水补助
    heating REAL,          -- S 取暖补助
    identity TEXT,        -- T 身份(策略名)
    product_class TEXT,   -- U 产品分类
    meter_type TEXT,      -- V 仪表类型
    comm_status TEXT,     -- W 通讯状态
    device_status TEXT,   -- X 设备状态
    install_addr TEXT,    -- Y 安装地址
    switch_status TEXT,   -- Z 开关状态
    switch_code TEXT,     -- AA 开关状态编码
    channel_name TEXT,    -- AB 通道名称
    channel TEXT,         -- AC 通道
    channel_no TEXT,      -- AD 通道号
    display_val REAL,     -- AE 显示值
    reading REAL,         -- AF 表读数
    gateway_no TEXT,      -- AG 网关号
    product_id_tag TEXT,  -- AH 产品标识
    product_id TEXT,      -- AI 产品ID
    comm_time TEXT,       -- AJ 通讯时间
    data_time TEXT,       -- AK 数据时间
    controllable TEXT,    -- AL 可控
    writable TEXT,        -- AM 可写
    atom_code TEXT,       -- AN 原子编码
    control_mode TEXT,   -- AO 控制模式
    pricing TEXT,        -- AP 计价方式
    balance_status TEXT, -- AQ 余额状态
    status TEXT,          -- AR 状态
    alarm_enabled TEXT,   -- AS 告警启用
    alarm_threshold TEXT, -- AT 告警阈值
    occupied TEXT,        -- AU 是否有人
    location TEXT,        -- AV 位置
    joint_control TEXT,   -- AW 合控命令启用
    comm_type TEXT,       -- AX 通讯类型
    signal_strength TEXT,  -- AY 信号强度
    battery_status TEXT,   -- AZ 电池状态
    ct_ratio TEXT,        -- BA CT变比
    pt_ratio TEXT,        -- BB PT变比
    meter_no TEXT,        -- BC 仪表编号
    version TEXT,         -- BD 表版本
    biz_format TEXT,      -- BE 业务格式
    -- BF 跳过(空列)
    project_name TEXT,    -- BG 项目名称(计算列)
    offline_hours REAL,   -- BH 离线时间(计算列)
    is_postpaid TEXT,     -- BI 是否签呈后付(计算列)
    fault_tag TEXT,       -- BJ 故障点(计算列)
    fault_desc TEXT       -- BK 故障描述(计算列)
);

-- 123设备原始数据 (123 sheet, 36列)
CREATE TABLE IF NOT EXISTS equipment_123 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_abbr TEXT,    -- A 项目简称
    device_group TEXT,    -- B 设备分组
    device_id TEXT,       -- C 设备ID
    device_name TEXT,     -- D 设备名称
    device_type TEXT,     -- E 设备类型
    device_tag TEXT,      -- F 设备标签
    online_status TEXT,   -- G 在线状态
    device_status TEXT,   -- H 设备状态
    sn_code TEXT,         -- I SN码
    imei TEXT,            -- J IMEI
    mac TEXT,             -- K MAC
    address TEXT,         -- L 地址
    longitude REAL,       -- M 经度
    latitude REAL,        -- N 纬度
    firmware TEXT,        -- O 固件版本
    last_comm TEXT,       -- P 最近通讯时间
    create_time TEXT,     -- Q 创建时间
    verify_code TEXT,     -- R 验证码
    protocol TEXT,        -- S 协议
    account TEXT,         -- T 设备账号
    update_time TEXT,     -- U 最后更新时间
    battery REAL,         -- V 电池电量
    signal REAL,          -- W 信号强度
    humidity REAL,        -- X 湿度
    temperature REAL,     -- Y 温度
    ext_power TEXT,       -- Z 外部供电
    report_time TEXT,     -- AA 上报时间
    formaldehyde REAL,    -- AB 甲醛浓度
    pm25 REAL,            -- AC PM2.5浓度
    co2 REAL,             -- AD CO2浓度
    tvoc REAL,            -- AE TVOC浓度
    water_immersion TEXT,  -- AF 水浸状态
    noise REAL,           -- AG 噪声值
    pressure REAL,        -- AH 压力
    project_name TEXT,    -- AI 标准项目名称(计算列)
    comm_delay REAL      -- AJ 通讯时差(计算列)
);

-- 安全履职 (安全履职 sheet, 12列)
CREATE TABLE IF NOT EXISTS safety_duty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,       -- A 时间戳
    plan_type TEXT,      -- B 计划类型
    start_date TEXT,     -- C 开始时间
    end_date TEXT,       -- D 结束时间
    plan_status TEXT,    -- E 计划状态
    plan_content TEXT,   -- F 计划内容
    position TEXT,       -- G 岗位名称
    responsible TEXT,    -- H 责任人
    unit TEXT,           -- I 责任单位(项目名)
    completion TEXT,     -- J 完成方式
    interval_days TEXT,  -- K 间隔周期(天)
    countdown REAL       -- L 结束倒计时(计算列)
);

-- 隐患核查 (隐患核查 sheet, 16列)
CREATE TABLE IF NOT EXISTS hazard_inspection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,   -- A 项目名称(计算列)
    category TEXT,       -- B 隐患类别
    level TEXT,          -- C 隐患级别
    responsible TEXT,    -- D 整改负责人
    deadline TEXT,       -- E 整改期限
    description TEXT,    -- F 隐患描述
    measure TEXT,        -- G 整改措施
    audit_status TEXT,   -- H 审核状态
    finish_time TEXT,    -- I 完成时间
    hazard_status TEXT,  -- J 隐患状态
    delay_days TEXT,     -- K 延期天数
    delay_note TEXT,     -- L 延期说明
    creator TEXT,        -- M 创建人
    create_time TEXT,    -- N 创建时间
    remaining_days REAL, -- O 剩余天数(计算列)
    create_days REAL     -- P 创建天数(计算列)
);

-- 末端水压 (末端水压 sheet, 16列)
CREATE TABLE IF NOT EXISTS water_pressure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,   -- A 所属项目(计算列)
    device_no TEXT,      -- B 设备编号
    net_signal TEXT,     -- C 网络信号
    probe_battery TEXT,  -- D 探测器电量
    module_battery TEXT, -- E 模块电量
    pressure REAL,       -- F 实时水压
    temperature REAL,    -- G 温度
    report_time TEXT,    -- H 上报时间
    device_name TEXT,    -- I 设备名称
    install_loc TEXT,    -- J 安装位置
    normal_status TEXT,  -- K 正常状态
    online_status TEXT,  -- L 在线状态
    col_m TEXT,          -- M (备用)
    col_n TEXT,          -- N (备用)
    comm_delay REAL,     -- O 通讯时间(计算列)
    pressure_fault TEXT  -- P 压力故障(计算列)
);

-- 商贸预算 (商贸预算 sheet, 11列)
CREATE TABLE IF NOT EXISTS commerce_budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT,        -- A 预算科目
    adjusted_budget REAL, -- B 追加后预算数
    period TEXT,         -- C 预算期间
    pending_cost REAL,   -- D 审批中费用
    initial_budget REAL, -- E 年初预算数
    actual_cost REAL,    -- F 实际发生数
    available_budget REAL, -- G 可用预算数
    revised_budget REAL, -- H 调整后预算数
    execution_rate REAL, -- I 执行占比
    unit TEXT,           -- J 预算单位
    additional_budget REAL -- K 预算追加数
);

-- 物业预算 (物业预算 sheet, 11列)
CREATE TABLE IF NOT EXISTS property_budget (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT,        -- A 预算科目
    adjusted_budget REAL, -- B 追加后预算数
    period TEXT,         -- C 预算期间
    pending_cost REAL,   -- D 审批中费用
    initial_budget REAL, -- E 年初预算数
    actual_cost REAL,    -- F 实际发生数
    available_budget REAL, -- G 可用预算数
    revised_budget REAL, -- H 调整后预算数
    execution_rate REAL, -- I 执行占比
    unit TEXT,           -- J 预算单位
    additional_budget REAL -- K 预算追加数
);

-- 后付费登记表 (后付费登记表 sheet, 6列)
CREATE TABLE IF NOT EXISTS postpaid_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_name TEXT,     -- A 仪表名称
    meter_no TEXT,       -- B 表号
    room_id TEXT,        -- C 房间id
    remark TEXT,         -- D 备注
    identity TEXT,       -- E 所属身份
    project_name TEXT   -- F 所属身份→项目名(计算列)
);

-- 已报备故障 (已报备故障 sheet, 16列)
CREATE TABLE IF NOT EXISTS reported_faults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT,      -- A 房间名称
    meter_name TEXT,     -- B 仪表名称
    balance REAL,        -- C 账户余额
    base_account REAL,   -- D 基本账户
    subsidy_account REAL, -- E 补助账户
    identity TEXT,       -- F 所属身份
    meter_type TEXT,     -- G 仪表类型
    reading REAL,        -- H 当前示数
    online_status TEXT,  -- I 在线状态
    meter_no TEXT,       -- J 仪表表号
    branch TEXT,         -- K 支路
    switch_detail TEXT,  -- L 开关详情
    comm_time TEXT,      -- M 通讯时间
    gateway_no TEXT,     -- N 网关号
    channel_no TEXT,     -- O 通道号
    project_name TEXT    -- P 项目名称(计算列)
);

-- ===================== 配置/映射表 =====================

-- 名称匹配 (名称匹配 sheet, 7列)
CREATE TABLE IF NOT EXISTS name_matching (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity TEXT,       -- A 身份策略
    pm_name TEXT,        -- B 物业负责人
    eng_name TEXT,       -- C 工程负责人
    eng_email TEXT,      -- D 工程负责人邮箱
    project_name TEXT,    -- E 项目名称
    erp_code TEXT,       -- F ERP代码
    project_123 TEXT     -- G 123项目名称
);

-- 身份匹配表 (身份匹配表 sheet)
CREATE TABLE IF NOT EXISTS identity_matching (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity TEXT,
    pm_name TEXT,
    eng_name TEXT,
    project_name TEXT,
    col_e TEXT,
    col_f TEXT,
    col_g TEXT,
    col_h TEXT
);

-- 导出列表_归属项目
CREATE TABLE IF NOT EXISTS project_attribution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,
    count INTEGER
);

-- 导出列表_隐患状态
CREATE TABLE IF NOT EXISTS hazard_status_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status_name TEXT,
    count INTEGER
);

-- ===================== 预算汇总(对照数据) =====================
-- 预算使用情况sheet的矩阵布局归一化为行记录
CREATE TABLE IF NOT EXISTS budget_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,    -- A 项目名称/单位
    category TEXT,        -- 类别名(商贸总预算/物业总预算等)
    current_usage REAL,   -- 当期用量
    current_rate TEXT,    -- 当期占比
    yearly_usage REAL,    -- 当年用量
    yearly_rate TEXT,     -- 当年占比
    sort_order INTEGER    -- 行号(用于排序)
);

-- ===================== 频道绑定 =====================
CREATE TABLE IF NOT EXISTS channel_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT,           -- feishu / wechat
    user_id TEXT,           -- 飞书open_id 或 微信user_id
    user_name TEXT,         -- 用户名/昵称
    context_token TEXT,     -- 微信iLink需要context_token才能发消息
    project_name TEXT,      -- 分配的项目(可空)
    created_at TEXT,
    last_active TEXT
);

-- ===================== 同步日志 =====================
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_time TEXT,      -- 同步时间
    source_file TEXT,    -- 源文件
    sheet_name TEXT,     -- sheet名
    rows_imported INTEGER, -- 导入行数
    status TEXT,         -- 状态(success/error)
    message TEXT         -- 消息
);

-- ===================== AI写库审计日志 =====================
CREATE TABLE IF NOT EXISTS ai_write_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator TEXT,       -- 操作者(admin标识)
    action TEXT,         -- register_fault / register_postpaid
    table_name TEXT,     -- reported_faults / postpaid_register
    payload TEXT,        -- 写入参数(JSON)
    result TEXT,         -- 执行结果(JSON, 含新增id或错误)
    created_at TEXT      -- 操作时间
);
"""


def init_db():
    """初始化数据库，创建所有表"""
    conn = get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print(f"数据库已初始化: {DB_PATH}")


def reset_db():
    """重置数据库（删除所有数据，保留表结构）"""
    conn = get_conn()
    tables = [
        'ruixin_meters', 'equipment_123', 'safety_duty', 'hazard_inspection',
        'water_pressure', 'commerce_budget', 'property_budget',
        'postpaid_register', 'reported_faults', 'name_matching',
        'identity_matching', 'project_attribution', 'hazard_status_list',
        'budget_summary', 'sync_log'
    ]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()
    conn.close()
    print("数据库已重置")


def get_table_info():
    """获取所有表信息"""
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    result = []
    for t in tables:
        name = t['name']
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
        result.append({
            'table': name,
            'rows': count,
            'columns': [c['name'] for c in cols]
        })
    conn.close()
    return result


if __name__ == '__main__':
    init_db()
    for t in get_table_info():
        print(f"{t['table']}: {t['rows']} rows, {len(t['columns'])} cols")
