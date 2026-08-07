# 金鹰集团数据管理中心

## 配置（部署前必读）

仓库不含任何真实凭证。部署前需准备以下配置文件（均提供 `.example` 模板，复制后填入真实值）：

1. **环境变量**：复制 `.env.example` 为 `.env`，设置 `AUTH_SECRET`（token 签名密钥，务必改为随机长字符串）、`JINYING_USER`/`JINYING_PASSWORD`（安全系统爬虫账号）
2. **`data/` 配置**：复制各 `*.json.example` 为对应 `*.json`，填入 AI API Key、飞书 App ID/Secret 等
3. **爬虫配置**：复制 `backend/crawlers/config.json.example` 为 `config.json`，填入瑞信/预算系统账号
4. **初始数据**：将 `总控表_集控表.xlsx` 放入 `data/`，首次启动自动导入

> ⚠️ `data/*.json`、`config.json`、`.env`、`center.db`、日志等均已在 `.gitignore` 中排除，请勿手动提交。

## 快速启动

### Windows
```bat
双击 start.bat
```

### Linux
```bash
chmod +x start.sh
./start.sh
```

启动后访问 `http://localhost:5000`

## 登录

| 角色 | 登录方式 | 密码 | 权限 |
|------|---------|------|------|
| 管理员 | 选"管理员(全部项目)" | 见 `data/admin_config.json`（首次部署为初始默认密码，登录后请修改） | 全部功能 |
| 项目用户 | 选对应项目名 | 由管理员在系统内配置 | 通知推送+AI对话 |

## 目录结构

```
data_center/
├── backend/                    # Flask 后端
│   ├── app.py                  # 主应用 (API + 静态托管 + 自动启动长连接)
│   ├── auth.py                 # 认证 (管理员+项目用户, token base64编码)
│   ├── db.py                   # SQLite 数据库 (14张表)
│   ├── sync.py                 # xlsx 数据同步 (17个sheet + 公式计算)
│   ├── sync_controller.py      # 集控中心爬虫调度 (路径已改为本地 crawlers/)
│   ├── calc.py                 # 计算引擎 (Excel公式→Python)
│   ├── ai.py                   # AI 对话 (全量数据 + SQL查询 + 会话记忆)
│   ├── notifier.py             # 通知推送 (微信iLink + 飞书WebSocket)
│   ├── requirements.txt        # Python 依赖
│   └── crawlers/               # 集控中心爬虫脚本
│       ├── ruixin_crawler.py   # 瑞信电表爬虫
│       ├── budget_crawler.py   # 预算管理爬虫
│       ├── sd123_crawler.py    # 123物联网设备爬虫
│       ├── jinying_crawler.py  # 金鹰安全管理爬虫
│       ├── sd123_mqtt.py       # 123 MQTT 实时监控
│       ├── config.json          # 爬虫配置 (账号密码)
│       └── sync_config.json     # 同步配置 (间隔/输出路径)
├── frontend/
│   └── dist/                  # 已构建的 Vue3 前端
├── data/                      # 运行时数据
│   ├── center.db              # SQLite 数据库 (22912行数据)
│   ├── 总控表_集控表.xlsx      # 初始数据文件 (首次启动自动导入)
│   ├── admin_config.json      # 认证配置 (31个项目密码=12345)
│   ├── ai_config.json         # AI 配置
│   ├── notify_config.json     # 通知配置
│   ├── wechat_token.json      # 微信 token
│   ├── wechat_users.json      # 已绑定用户
│   └── feishu_creds.json      # 飞书凭证
├── start.bat                  # Windows 启动
├── start.sh                  # Linux 启动
└── README.md
```

## 依赖

### Python (后端)
```
pip install -r backend/requirements.txt
```
- Flask + Flask-CORS
- openpyxl + pandas (xlsx 解析)
- requests (HTTP 调用)
- segno (二维码生成)
- lark-oapi (飞书 WebSocket)

### Node.js (仅重新构建前端时需要，已预构建)
```
cd frontend && npm install && npm run build
```

## 功能

### 数据看板 (5页, 全部可排序)
- **集团总览**: 6个KPI + 4个ECharts图表
- **瑞信电表**: 29个项目排名表
- **金鹰安全**: 41个项目多级表头
- **设备管理**: 23个项目进度条故障率
- **预算使用**: 15类别切换 + 75单位占比

### AI 助手 (浮球浮窗)
- 全量数据上下文注入 (所有项目)
- 数据库明细查询 (AI 自动生成SQL → 执行 → 回答)
- 按用户ID隔离的会话记忆
- 微信/飞书用户可直接对话

### 通知推送 (独立, 不依赖QwenPaw)
- **微信**: 扫码登录 → long-poll → AI 回复 + 日报推送
- **飞书**: 扫码绑定 → WebSocket 长连接 → AI 回复 + 日报推送
- 每日定时推送管理日报
- 消息去重 (防止重复处理旧消息)

### 数据同步 (集控中心)
- 4 个爬虫模块 (瑞信/预算/123设备/金鹰安全)
- 爬虫输出 xlsx → 自动导入 SQLite
- sheet 名别名映射 + 公式列 Python 重算

### 认证权限
- 管理员: 全部功能
- 项目用户: 通知推送 + AI 对话 (只能看自己的项目)
- token 使用 base64 编码项目名 (HTTP header 兼容)

## 部署

### 1. 拷贝 data_center/ 到服务器
### 2. 安装依赖
```bash
pip install -r backend/requirements.txt
```
### 3. 启动
```bash
python backend/app.py
```
### 4. (可选) Gunicorn
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app
```

## 注意事项
- 微信用户需先发一条消息给 bot (获取 context_token)
- 飞书扫码绑定后自动建立 WebSocket (不需要公网IP)
- 爬虫脚本在 `backend/crawlers/` 目录, 配置在 `config.json`
- 初始 xlsx 在 `data/总控表_集控表.xlsx`, 首次启动自动导入
- 前端已预构建, 不需要 Node.js
