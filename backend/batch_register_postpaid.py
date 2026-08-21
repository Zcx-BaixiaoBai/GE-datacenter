"""
泰州金鹰天地 30 块无签呈后付费电表 → 批量登记后付费签呈
使用系统自身的 _execute_register_postpaid() 逻辑，与 AI 走同一条路：
  - 字段白名单 + ?占位符
  - 写前查重（已登记的跳过）
  - 审计日志
  - 写后重算公式列
"""
import sys, os, sqlite3
from datetime import datetime

# 确保能 import ai 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import ai

DB = ai.DB_PATH
OPERATOR = 'admin-batch'
PROJECT = '泰州金鹰天地'
REMARK = '泰州金鹰天地30块无签呈后付费批量登记'

print(f"=== 批量后付费登记 ===")
print(f"项目: {PROJECT}")
print(f"操作者: {OPERATOR}")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 1. 查出 30 块无签呈后付费电表
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT room_id, install_addr, room, project_name FROM ruixin_meters "
    "WHERE project_name=? AND fault_tag LIKE '%无签呈后付费%' ORDER BY room",
    (PROJECT,)
).fetchall()
conn.close()
print(f"查到 {len(rows)} 块无签呈后付费电表\n")

# 2. 逐块登记
ok, skip, fail = 0, 0, 0
for i, r in enumerate(rows, 1):
    params = {
        'room_id': str(r['room_id']),
        'project_name': r['project_name'],
        'meter_no': r['install_addr'],
        'meter_name': r['room'],
        'remark': REMARK,
    }
    result = ai._execute_register_postpaid(params, operator=OPERATOR)
    status = '✅成功' if result.get('ok') else ('⏭重复' if '重复' in result.get('error', '') else '❌失败')
    if result.get('ok'):
        ok += 1
    elif '重复' in result.get('error', ''):
        skip += 1
    else:
        fail += 1
    print(f"[{i:2d}/30] {status} room_id={r['room_id']} | {r['room']} | {r['install_addr']}")

print(f"\n--- 登记结果 ---")
print(f"成功: {ok}  重复跳过: {skip}  失败: {fail}")

# 3. 重算公式列（消除故障标记）
print(f"\n--- 重算公式列 ---")
try:
    recalc = ai._recalc_formula_columns()
    print(f"重算结果: {recalc}")
except Exception as e:
    print(f"重算失败: {e}")

# 4. 验证：重新查这 30 块的 fault_tag 是否已消除
print(f"\n--- 验证 ---")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
remaining = conn.execute(
    "SELECT count(*) as cnt FROM ruixin_meters "
    "WHERE project_name=? AND fault_tag LIKE '%无签呈后付费%'",
    (PROJECT,)
).fetchone()
print(f"泰州金鹰天地剩余无签呈后付费电表: {remaining['cnt']} 块")

# 检查 postpaid_register 表确认写入
registered = conn.execute(
    "SELECT count(*) as cnt FROM postpaid_register WHERE room_id IN "
    "(SELECT room_id FROM ruixin_meters WHERE project_name=?)",
    (PROJECT,)
).fetchone()
print(f"postpaid_register 表中泰州相关记录: {registered['cnt']} 条")
conn.close()

print(f"\n=== 完成 ===")
