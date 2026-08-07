"""
金鹰集团数据管理中心 - 计算引擎
将集控中心Excel公式转为Python算法，复刻所有汇总sheet的计算逻辑

复刻的Excel公式:
  瑞信电表: COUNTIF/COUNTIFS故障分类 + RANK排名 + IF评级(优/良/差)
  金鹰安全: COUNTIFS隐患/履职统计 + 水压设备状态
  123设备管理: COUNTIF设备总数 + COUNTIFS故障数(通讯时差>=90天)
  预算使用情况: 预算汇总对照数据 + 原始预算计算
"""
from db import get_conn


# ─── 瑞信电表 ──────────────────────────────────────────────

def calc_meters():
    """
    瑞信电表计算 - 复刻Excel公式
    C =COUNTIF(ruixin!BG:BG, project)         总表具数量
    D =C-COUNTIFS(ruixin!BG,project,ruixin!BJ,"")  故障电表数量
    E =F/C                                     离线率
    F =COUNTIFS(ruixin!BJ,"*离线*",ruixin!BG,project)  离线
    G =COUNTIFS(ruixin!BJ,"*异常送电*",ruixin!BG,project)  异常送电
    H =COUNTIFS(ruixin!BJ,"*无签呈后付费*",ruixin!BG,project)  无签呈后付费
    Q =D/C                                     故障率
    R =RANK(Q, Q列, 1)                        排名(升序)
    K =IF(OR(R<=10,Q=0),"优",IF(OR(R>=23,Q>Q$2),"差","良"))  管理评价
    I =XLOOKUP(project, 名称匹配!E:E, 名称匹配!B:B)  项目负责人
    J =XLOOKUP(project, 名称匹配!E:E, 名称匹配!C:C)  工程负责人
    L =XLOOKUP(project, 名称匹配!E:E, 名称匹配!D:D)  工程负责人邮箱
    """
    conn = get_conn()

    # 名称匹配映射
    name_map = {}
    for r in conn.execute("SELECT project_name, pm_name, eng_name, eng_email FROM name_matching"):
        if r['project_name']:
            name_map[r['project_name']] = {
                'pm_name': r['pm_name'] or '',
                'eng_name': r['eng_name'] or '',
                'eng_email': r['eng_email'] or ''
            }

    # 按项目统计电表数据
    rows = conn.execute("""
        SELECT project_name,
               COUNT(*) as total,
               SUM(CASE WHEN fault_tag IS NULL OR fault_tag = '' THEN 1 ELSE 0 END) as normal,
               SUM(CASE WHEN fault_tag LIKE '%离线%' THEN 1 ELSE 0 END) as offline,
               SUM(CASE WHEN fault_tag LIKE '%异常送电%' THEN 1 ELSE 0 END) as abnormal,
               SUM(CASE WHEN fault_tag LIKE '%无签呈后付费%' THEN 1 ELSE 0 END) as unpaid
        FROM ruixin_meters
        WHERE project_name IS NOT NULL AND project_name != ''
        GROUP BY project_name
        ORDER BY total DESC
    """).fetchall()

    projects = []
    for r in rows:
        total = r['total']
        normal = r['normal']
        fault = total - normal
        offline = r['offline']
        abnormal = r['abnormal']
        unpaid = r['unpaid']
        fault_rate = round(fault / total, 4) if total > 0 else 0
        offline_rate = round(offline / total, 4) if total > 0 else 0
        proj_name = r['project_name']
        nm = name_map.get(proj_name, {})
        projects.append({
            'project_name': proj_name,
            'total': total,
            'fault': fault,
            'offline': offline,
            'abnormal': abnormal,
            'unpaid': unpaid,
            'fault_rate': fault_rate,
            'offline_rate': offline_rate,
            'pm_name': nm.get('pm_name', ''),
            'eng_name': nm.get('eng_name', ''),
            'eng_email': nm.get('eng_email', ''),
        })

    # RANK排名: 按故障率升序(故障率低的排名靠前=优)
    # Excel RANK(Q, Q列, 1) 中 order=1 表示升序排名
    sorted_by_rate = sorted(projects, key=lambda x: x['fault_rate'])
    for i, p in enumerate(sorted_by_rate):
        p['rank'] = i + 1

    # 计算平均故障率(Q$2 = 集团汇总故障率)
    total_meters = sum(p['total'] for p in projects)
    total_faults = sum(p['fault'] for p in projects)
    avg_fault_rate = total_faults / total_meters if total_meters > 0 else 0

    # 管理评价: IF(OR(R<=10,Q=0),"优",IF(OR(R>=23,Q>avg),"差","良"))
    total_projects = len(projects)
    for p in projects:
        rank = p['rank']
        q = p['fault_rate']
        if rank <= 10 or q == 0:
            p['evaluation'] = '优'
        elif rank >= total_projects - 4 or q > avg_fault_rate:
            p['evaluation'] = '差'
        else:
            p['evaluation'] = '良'

    # 集团汇总
    summary = {
        'project_name': '集团汇总',
        'total': total_meters,
        'fault': total_faults,
        'offline': sum(p['offline'] for p in projects),
        'abnormal': sum(p['abnormal'] for p in projects),
        'unpaid': sum(p['unpaid'] for p in projects),
        'fault_rate': round(avg_fault_rate, 4),
        'offline_rate': round(sum(p['offline'] for p in projects) / total_meters, 4) if total_meters > 0 else 0,
        'evaluation': '-',
        'rank': 0,
        'pm_name': '', 'eng_name': '', 'eng_email': '',
    }

    conn.close()
    return {'summary': summary, 'projects': projects, 'avg_fault_rate': round(avg_fault_rate, 4)}


# ─── 金鹰安全 ──────────────────────────────────────────────

def calc_safety():
    """
    金鹰安全计算 - 复刻Excel公式
    I =COUNTIFS(隐患核查!A,project, C,"一般隐患", P,"<=31")     一般隐患
    J =COUNTIFS(..., C,"严重隐患", P,"<=31")                     严重隐患
    K =COUNTIFS(..., C,"重大隐患", P,"<=31")                     重大隐患
    L =COUNTIFS(隐患核查!A,project, J,"<>已整改", O,"<0")       逾期未完成
    M =COUNTIFS(..., J,"<>已整改", O,">=0", O,"<3")              即将逾期
    N =COUNTIFS(..., J,"<>已整改", O,">=3")                       未完成
    O =COUNTIFS(安全履职!I,project, E,"已完成", L,"<=31")       已完成
    P =COUNTIFS(..., E,"逾期完成", L,"<=31")                     逾期完成
    Q =COUNTIFS(..., E,"已开始", L,"<=31")                        已开始
    R =COUNTIFS(安全履职!I,project, E,"已逾期")                  已逾期(无日期过滤)
    S =COUNTIFS(..., E,"报备中", L,"<=31")                        报备中
    T =COUNTIFS(末端水压!A,project, P,"失压")                    失压
    U =COUNTIFS(..., P,"超压")                                    超压
    V =COUNTIFS(末端水压!A,project, O,">=2")                      离线(通讯时差>=2天)
    """
    conn = get_conn()

    # 获取所有涉及的项目名称(取并集)
    projects_set = set()
    for table, col in [('safety_duty', 'unit'), ('hazard_inspection', 'project_name'), ('water_pressure', 'project_name')]:
        for r in conn.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"):
            projects_set.add(r[col])
    projects = sorted(projects_set)

    results = []
    for proj in projects:
        # 隐患核查统计
        hazard_general = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND level=? AND create_days <= 31
        """, (proj, '一般隐患')).fetchone()[0]

        hazard_serious = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND level=? AND create_days <= 31
        """, (proj, '严重隐患')).fetchone()[0]

        hazard_major = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND level=? AND create_days <= 31
        """, (proj, '重大隐患')).fetchone()[0]

        # 逾期/即将逾期/未完成
        overdue = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND hazard_status != '已整改' AND remaining_days < 0
        """, (proj,)).fetchone()[0]

        imminent = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND hazard_status != '已整改' AND remaining_days >= 0 AND remaining_days < 3
        """, (proj,)).fetchone()[0]

        pending = conn.execute("""
            SELECT COUNT(*) FROM hazard_inspection
            WHERE project_name=? AND hazard_status != '已整改' AND remaining_days >= 3
        """, (proj,)).fetchone()[0]

        # 安全履职统计
        duty_completed = conn.execute("""
            SELECT COUNT(*) FROM safety_duty
            WHERE unit=? AND plan_status=? AND countdown <= 31
        """, (proj, '已完成')).fetchone()[0]

        duty_overdue_done = conn.execute("""
            SELECT COUNT(*) FROM safety_duty
            WHERE unit=? AND plan_status=? AND countdown <= 31
        """, (proj, '逾期完成')).fetchone()[0]

        duty_started = conn.execute("""
            SELECT COUNT(*) FROM safety_duty
            WHERE unit=? AND plan_status=? AND countdown <= 31
        """, (proj, '已开始')).fetchone()[0]

        duty_overdue = conn.execute("""
            SELECT COUNT(*) FROM safety_duty
            WHERE unit=? AND plan_status=?
        """, (proj, '已逾期')).fetchone()[0]

        duty_reporting = conn.execute("""
            SELECT COUNT(*) FROM safety_duty
            WHERE unit=? AND plan_status=? AND countdown <= 31
        """, (proj, '报备中')).fetchone()[0]

        # 水压设备
        wp_low = conn.execute("""
            SELECT COUNT(*) FROM water_pressure
            WHERE project_name=? AND pressure_fault='失压'
        """, (proj,)).fetchone()[0]

        wp_high = conn.execute("""
            SELECT COUNT(*) FROM water_pressure
            WHERE project_name=? AND pressure_fault='超压'
        """, (proj,)).fetchone()[0]

        wp_offline = conn.execute("""
            SELECT COUNT(*) FROM water_pressure
            WHERE project_name=? AND comm_delay >= 2
        """, (proj,)).fetchone()[0]

        results.append({
            'project_name': proj,
            'hazard_general': hazard_general,
            'hazard_serious': hazard_serious,
            'hazard_major': hazard_major,
            'overdue': overdue,
            'imminent': imminent,
            'pending': pending,
            'duty_completed': duty_completed,
            'duty_overdue_done': duty_overdue_done,
            'duty_started': duty_started,
            'duty_overdue': duty_overdue,
            'duty_reporting': duty_reporting,
            'wp_low': wp_low,
            'wp_high': wp_high,
            'wp_offline': wp_offline,
        })

    # 集团汇总
    summary = {
        'project_name': '集团汇总',
        'hazard_general': sum(r['hazard_general'] for r in results),
        'hazard_serious': sum(r['hazard_serious'] for r in results),
        'hazard_major': sum(r['hazard_major'] for r in results),
        'overdue': sum(r['overdue'] for r in results),
        'imminent': sum(r['imminent'] for r in results),
        'pending': sum(r['pending'] for r in results),
        'duty_completed': sum(r['duty_completed'] for r in results),
        'duty_overdue_done': sum(r['duty_overdue_done'] for r in results),
        'duty_started': sum(r['duty_started'] for r in results),
        'duty_overdue': sum(r['duty_overdue'] for r in results),
        'duty_reporting': sum(r['duty_reporting'] for r in results),
        'wp_low': sum(r['wp_low'] for r in results),
        'wp_high': sum(r['wp_high'] for r in results),
        'wp_offline': sum(r['wp_offline'] for r in results),
    }

    conn.close()
    return {'summary': summary, 'projects': results}


# ─── 123设备管理 ───────────────────────────────────────────

def calc_equipment():
    """
    123设备管理计算 - 复刻Excel公式
    C =COUNTIF('123'!AI:AI, project)           总设备
    D =COUNTIFS('123'!AI:AI,project, AJ:AJ,">=90")  故障数(通讯时差>=90天)
    """
    conn = get_conn()

    rows = conn.execute("""
        SELECT project_name,
               COUNT(*) as total,
               SUM(CASE WHEN comm_delay >= 90 THEN 1 ELSE 0 END) as fault
        FROM equipment_123
        WHERE project_name IS NOT NULL AND project_name != ''
        GROUP BY project_name
        ORDER BY total DESC
    """).fetchall()

    projects = []
    for r in rows:
        total = r['total']
        fault = r['fault'] or 0
        projects.append({
            'project_name': r['project_name'],
            'total': total,
            'fault': fault,
            'fault_rate': round(fault / total, 4) if total > 0 else 0,
        })

    summary = {
        'project_name': '集团汇总',
        'total': sum(p['total'] for p in projects),
        'fault': sum(p['fault'] for p in projects),
        'fault_rate': round(sum(p['fault'] for p in projects) / sum(p['total'] for p in projects), 4) if projects else 0,
    }

    conn.close()
    return {'summary': summary, 'projects': projects}


# ─── 预算使用情况 ──────────────────────────────────────────

def calc_budget():
    """
    预算使用情况 - 预算汇总对照数据 + 原始预算计算
    预算使用情况sheet(无公式, 预计算值)作为对照数据源
    商贸预算/物业预算原始数据作为计算算法
    """
    conn = get_conn()

    # 1. 对照数据(来自预算使用情况sheet)
    categories = [
        '商贸总预算', '商贸超市费用', '商贸工程维材费', '商贸商品调改',
        '商贸维保检测费', '商贸维修改造', '商贸综管维材费',
        '物业总预算', '3.1维保类', '3.2检测类', '4.1工程材料类',
        '4.2综管材料类', '5.1零星维修', '5.2专项改造', '5.3品质提升'
    ]

    projects_data = {}
    for r in conn.execute("""
        SELECT project_name, category, current_usage, current_rate,
               yearly_usage, yearly_rate, sort_order
        FROM budget_summary
        ORDER BY sort_order, category
    """).fetchall():
        proj = r['project_name']
        if proj not in projects_data:
            projects_data[proj] = {'project_name': proj, 'sort_order': r['sort_order'], 'categories': {}}
        projects_data[proj]['categories'][r['category']] = {
            'current_usage': r['current_usage'],
            'current_rate': r['current_rate'],
            'yearly_usage': r['yearly_usage'],
            'yearly_rate': r['yearly_rate'],
        }

    # 2. 原始预算计算(从商贸预算/物业预算表)
    # 按预算单位+科目聚合: 当期用量=最新期间实际发生, 当年用量=全部期间合计
    budget_calc = {}
    for table_name in ['commerce_budget', 'property_budget']:
        rows = conn.execute(f"""
            SELECT unit, subject,
                   SUM(actual_cost) as total_actual,
                   SUM(adjusted_budget) as total_adjusted,
                   SUM(CASE WHEN period LIKE '%一期%' OR period LIKE '%一季度%' THEN actual_cost ELSE 0 END) as current_actual
            FROM {table_name}
            WHERE unit IS NOT NULL AND unit != ''
            GROUP BY unit, subject
        """).fetchall()
        for r in rows:
            key = f"{r['unit']}_{r['subject']}"
            budget_calc[key] = {
                'unit': r['unit'],
                'subject': r['subject'],
                'current_usage': r['current_actual'] or 0,
                'yearly_usage': r['total_actual'] or 0,
                'yearly_budget': r['total_adjusted'] or 0,
                'yearly_rate': round((r['total_actual'] or 0) / r['total_adjusted'], 4) if r['total_adjusted'] else 0,
            }

    # 集团汇总行
    summary_row = projects_data.get('集团汇总', {})

    conn.close()
    return {
        'summary': summary_row,
        'projects': list(projects_data.values()),
        'categories': categories,
        'budget_calc': list(budget_calc.values()),
    }


# ─── 集团总览KPI ───────────────────────────────────────────

def calc_summary():
    """集团总览KPI - 汇总四大板块核心指标"""
    meters = calc_meters()
    safety = calc_safety()
    equipment = calc_equipment()

    m_sum = meters['summary']
    s_sum = safety['summary']
    e_sum = equipment['summary']

    return {
        'meters': {
            'total': m_sum['total'],
            'fault': m_sum['fault'],
            'offline': m_sum['offline'],
            'abnormal': m_sum['abnormal'],
            'unpaid': m_sum['unpaid'],
            'fault_rate': m_sum['fault_rate'],
            'project_count': len(meters['projects']),
        },
        'safety': {
            'hazard_total': s_sum['hazard_general'] + s_sum['hazard_serious'] + s_sum['hazard_major'],
            'hazard_overdue': s_sum['overdue'],
            'hazard_imminent': s_sum['imminent'],
            'duty_total': s_sum['duty_completed'] + s_sum['duty_overdue_done'] + s_sum['duty_started'] + s_sum['duty_overdue'] + s_sum['duty_reporting'],
            'duty_overdue': s_sum['duty_overdue'],
            'wp_low': s_sum['wp_low'],
            'wp_high': s_sum['wp_high'],
            'project_count': len(safety['projects']),
        },
        'equipment': {
            'total': e_sum['total'],
            'fault': e_sum['fault'],
            'fault_rate': e_sum['fault_rate'],
            'project_count': len(equipment['projects']),
        },
        'sync_info': _get_sync_info(),
    }


def _get_sync_info():
    """获取同步信息"""
    conn = get_conn()
    row = conn.execute("SELECT sync_time, source_file FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return {'last_sync': row['sync_time'], 'source_file': row['source_file']}
    return {'last_sync': None, 'source_file': None}


# ─── 命令行测试 ────────────────────────────────────────────

if __name__ == '__main__':
    import json

    print("=" * 60)
    print("瑞信电表计算结果:")
    print("=" * 60)
    meters = calc_meters()
    print(f"集团汇总: 总表{meters['summary']['total']}, 故障{meters['summary']['fault']}, "
          f"离线{meters['summary']['offline']}, 异常送电{meters['summary']['abnormal']}, "
          f"无签呈{meters['summary']['unpaid']}, 故障率{meters['summary']['fault_rate']:.2%}")
    print(f"平均故障率: {meters['avg_fault_rate']:.2%}")
    print(f"\n项目明细(前10):")
    for p in meters['projects'][:10]:
        print(f"  {p['rank']:2d}. {p['project_name']:<16} 总{p['total']:4d} 故障{p['fault']:3d} "
              f"离线{p['offline']:2d} 异常{p['abnormal']:2d} 无签{p['unpaid']:2d} "
              f"率{p['fault_rate']:.2%} [{p['evaluation']}]")

    print("\n" + "=" * 60)
    print("金鹰安全计算结果:")
    print("=" * 60)
    safety = calc_safety()
    s = safety['summary']
    print(f"集团汇总: 一般隐患{s['hazard_general']} 严重{s['hazard_serious']} 重大{s['hazard_major']} "
          f"逾期{s['overdue']} 即将逾期{s['imminent']} 未完成{s['pending']}")
    print(f"  履职: 完成{s['duty_completed']} 逾期完成{s['duty_overdue_done']} "
          f"已开始{s['duty_started']} 已逾期{s['duty_overdue']} 报备{s['duty_reporting']}")
    print(f"  水压: 失压{s['wp_low']} 超压{s['wp_high']} 离线{s['wp_offline']}")

    print("\n" + "=" * 60)
    print("123设备管理计算结果:")
    print("=" * 60)
    equip = calc_equipment()
    print(f"集团汇总: 总设备{equip['summary']['total']}, 故障{equip['summary']['fault']}, "
          f"故障率{equip['summary']['fault_rate']:.2%}")
    for p in equip['projects'][:5]:
        print(f"  {p['project_name']:<16} 总{p['total']:3d} 故障{p['fault']:3d} 率{p['fault_rate']:.2%}")

    print("\n" + "=" * 60)
    print("集团总览KPI:")
    print("=" * 60)
    summary = calc_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
