"""演示数据初始化：角色、用户、设备、故障代码、备件、知识库、历史工单。"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.base import (
    EquipmentStatusEnum,
    FaultReportStatusEnum,
    KnowledgeCategoryEnum,
    MaintenanceLogTypeEnum,
    PriorityEnum,
    RiskLevelEnum,
    UrgencyEnum,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)
from app.models.equipment import Equipment, EquipmentType, FaultCode, SparePart
from app.models.fault import FaultReport
from app.models.knowledge import KnowledgeArticle
from app.models.maintenance import LaborEntry, MaintenanceLog, WorkOrderSparePart
from app.models.user import Skill, TechnicianProfile, User
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)

DEMO_PASSWORD = "Demo123456"

SKILLS = ["电气维修", "机械维修", "PLC编程", "气动液压", "伺服调试", "焊接", "机器人维护", "仪表校准"]

EQUIPMENT_TYPES = [
    ("数控机床", "CNC 加工中心类设备"),
    ("包装机", "自动化包装产线设备"),
    ("空压机", "压缩空气供给设备"),
    ("输送机", "物料输送带及链条设备"),
    ("工业机器人", "六轴及 SCARA 工业机器人"),
]

FAULT_CODES = [
    ("E101", "伺服驱动报警", "high", "数控机床"),
    ("E102", "控制柜异常", "high", "包装机"),
    ("E103", "电机温度过高", "medium", "数控机床"),
    ("E104", "接近开关信号异常", "low", "包装机"),
    ("E105", "气压不足", "medium", "空压机"),
    ("E106", "输送带跑偏", "medium", "输送机"),
    ("E107", "机器人定位偏差", "high", "工业机器人"),
    ("E108", "润滑系统压力异常", "medium", "数控机床"),
    ("E109", "变频器过载", "high", "输送机"),
    ("E110", "气缸动作异常", "low", "包装机"),
]

SPARE_PARTS = [
    ("SP001", "接近开关", "电感式 NPN NO", "个"),
    ("SP002", "伺服驱动器", "750W 220V", "台"),
    ("SP003", "接触器", "AC220V 32A", "个"),
    ("SP004", "空气滤芯", "标准型", "个"),
    ("SP005", "输送带", "PVC 100mm", "米"),
    ("SP006", "减速机油", "ISO VG220", "升"),
    ("SP007", "编码器", "增量式 1024PPR", "个"),
    ("SP008", "电磁阀", "DC24V 二位五通", "个"),
    ("SP009", "轴承", "6204ZZ", "个"),
    ("SP010", "变频器", "5.5kW", "台"),
]

PLANTS = ["一厂区", "二厂区"]
LINES = ["A 产线", "B 产线", "C 产线", "包装线", "装配线"]

KNOWLEDGE = [
    ("E101 伺服驱动报警排查指南", KnowledgeCategoryEnum.fault_code, "当数控机床出现 E101 伺服驱动报警时，通常由驱动器过载、编码器反馈异常或参数丢失引起。排查步骤：1. 检查驱动器报警代码并记录；2. 测量电机绝缘；3. 检查编码器接线；4. 必要时复位参数。安全提示：断电后等待 5 分钟让电容放电完毕再操作。", ["伺服", "E101", "驱动器"], "数控机床"),
    ("包装机接近开关维护 SOP", KnowledgeCategoryEnum.sop, "包装机接近开关每周清洁一次，每月检查安装紧固情况。安装松动会导致检测信号异常 E104。更换时注意型号一致，感应距离 2mm。", ["接近开关", "E104", "包装机"], "包装机"),
    ("控制柜电气安全操作规程", KnowledgeCategoryEnum.safety, "进入控制柜作业前必须执行 LOTO 上锁挂牌：1. 主电源断电并挂锁；2. 验电确认无电压；3. 释放残余能量；4. 作业完成后由本人摘锁。严禁带电作业，严禁短接安全联锁。", ["安全", "LOTO", "电气"], None),
    ("空压机气压不足处理经验", KnowledgeCategoryEnum.experience, "气压不足常见原因：进气滤芯堵塞、安全阀泄漏、管路接头松动。先检查滤芯压差，再听阀件有无漏气声。更换滤芯后一般可恢复。", ["气压", "E105", "空压机"], "空压机"),
    ("输送带跑偏调整方法", KnowledgeCategoryEnum.experience, "输送带跑偏 E106 调整原则：跑哪侧紧哪侧。松开张紧螺栓，微调两侧张紧量，空载运行观察 10 分钟，再逐步加载测试。", ["跑偏", "E106", "输送带"], "输送机"),
    ("机器人定位偏差校准流程", KnowledgeCategoryEnum.sop, "工业机器人出现定位偏差 E107 时：1. 检查零点是否丢失；2. 执行零点标定；3. 校准工具坐标系；4. 复跑程序验证重复定位精度。", ["机器人", "E107", "定位"], "工业机器人"),
    ("润滑系统压力异常诊断", KnowledgeCategoryEnum.case, "某数控机床 E108 润滑压力异常，经查为润滑泵滤网堵塞导致供油不足。清洗滤网、更换润滑油后压力恢复正常。建议每季度更换润滑油。", ["润滑", "E108"], "数控机床"),
    ("变频器过载故障案例分析", KnowledgeCategoryEnum.case, "输送机变频器频繁报过载 E109，根因为负载侧轴承卡阻导致电流增大。更换轴承 6204ZZ 后故障消除。", ["变频器", "E109", "过载"], "输送机"),
    ("预防性维护计划模板", KnowledgeCategoryEnum.sop, "设备预防性维护周期：每日点检、每周清洁、每月润滑、每季度精度检查、每年大修。建立维护台账并跟踪执行情况。", ["预防性维护", "PM"], None),
    ("上锁挂牌（LOTO）标准程序", KnowledgeCategoryEnum.safety, "LOTO 六步法：通知、关停、隔离、上锁、释放能量、验证。维修完成后反向解除。任何维修开始前必须完成 LOTO。", ["LOTO", "安全"], None),
    ("E103 电机温度过高处理", KnowledgeCategoryEnum.fault_code, "电机温度过高 E103 常见原因：过载运行、散热风扇故障、轴承磨损、环境温度过高。检查负载率、测量轴承振动、清洁风道。", ["E103", "电机", "温度"], "数控机床"),
    ("气缸动作异常排查", KnowledgeCategoryEnum.fault_code, "气缸动作异常 E110：检查气源压力、电磁阀换向、气缸密封。常见为密封圈老化内漏，更换密封件即可。", ["E110", "气缸"], "包装机"),
    ("设备二维码管理说明", KnowledgeCategoryEnum.experience, "每台设备配置唯一二维码，扫码可直接进入设备详情页查看历史工单与维修记录，便于现场快速定位设备。", ["二维码", "管理"], None),
    ("维修记录规范要求", KnowledgeCategoryEnum.sop, "维修记录应包含：检查发现、根本原因、处理措施、更换部件、测试结果、工时。语言客观专业，避免口语化。可使用 AI 辅助润色但需保留原始记录。", ["维修记录", "规范"], None),
    ("验收标准与退回处理", KnowledgeCategoryEnum.sop, "工单完工后由主管验收。验收标准：必填项齐全、测试通过、设备恢复正常。不合格退回并填写原因，工程师修改后重新提交。", ["验收", "规范"], None),
]

# (故障描述模板, 对应故障代码, 对应设备类型)
FAULT_TEMPLATES = [
    ("{eq} 伺服驱动器报警 E101，无法启动", "E101", "数控机床"),
    ("{eq} 控制柜有异响，屏幕显示 E102", "E102", "包装机"),
    ("{eq} 主轴电机温度过高 E103", "E103", "数控机床"),
    ("{eq} 接近开关信号异常 E104，检测不稳定", "E104", "包装机"),
    ("{eq} 气压不足 E105，无法达到工作压力", "E105", "空压机"),
    ("{eq} 输送带跑偏 E106", "E106", "输送机"),
    ("{eq} 机器人定位偏差 E107", "E107", "工业机器人"),
    ("{eq} 润滑系统压力异常 E108", "E108", "数控机床"),
    ("{eq} 变频器过载 E109", "E109", "输送机"),
    ("{eq} 气缸动作异常 E110", "E110", "包装机"),
]

ROOT_CAUSES = {
    "E101": "伺服驱动器编码器接线松动导致反馈异常",
    "E102": "控制柜内接触器触点烧蚀产生异响",
    "E103": "电机散热风扇损坏导致温升",
    "E104": "接近开关安装松动导致检测距离变化",
    "E105": "进气滤芯堵塞导致供气不足",
    "E106": "输送带两侧张紧不一致导致跑偏",
    "E107": "机器人零点丢失导致定位偏差",
    "E108": "润滑泵滤网堵塞导致供油压力异常",
    "E109": "负载侧轴承卡阻导致变频器过载",
    "E110": "气缸密封圈老化导致内漏",
}

ACTIONS = {
    "E101": "重新紧固编码器接线并复位驱动器参数",
    "E102": "更换烧蚀的接触器并清理触点",
    "E103": "更换散热风扇并清洁风道",
    "E104": "重新紧固接近开关并调整感应距离",
    "E105": "更换进气滤芯并检查管路密封",
    "E106": "调整输送带张紧量并空载测试",
    "E107": "执行机器人零点标定并校准工具坐标系",
    "E108": "清洗润滑泵滤网并更换润滑油",
    "E109": "更换负载侧轴承 6204ZZ",
    "E110": "更换气缸密封圈",
}

PARTS_USED = {
    "E101": "编码器接线端子",
    "E102": "接触器 AC220V 32A",
    "E103": "散热风扇",
    "E104": "接近开关",
    "E105": "空气滤芯",
    "E106": "",
    "E107": "",
    "E108": "减速机油 ISO VG220",
    "E109": "轴承 6204ZZ",
    "E110": "气缸密封圈",
}


def _wo_code(db: Session, i: int) -> str:
    year = datetime.now(timezone.utc).year
    return f"WO-{year}-{i:04d}"


def run_seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        _seed(db)
        db.commit()
        print("[seed] 演示数据初始化完成")
    except Exception as e:
        db.rollback()
        print(f"[seed] 演示数据初始化失败: {e}")
    finally:
        db.close()


def _seed(db: Session) -> None:
    random.seed(42)
    # 用户
    admin = User(email="admin@example.com", hashed_password=hash_password(DEMO_PASSWORD), full_name="系统管理员", phone="13800000001", role="admin")  # type: ignore[arg-type]
    sup = User(email="supervisor@example.com", hashed_password=hash_password(DEMO_PASSWORD), full_name="张主管", phone="13800000002", role="supervisor")  # type: ignore[arg-type]
    techs_data = [
        ("tech@example.com", "演示工程师", "电气维修,PLC编程,伺服调试"),
        ("tech1@example.com", "李工程师", "电气维修,PLC编程,伺服调试"),
        ("tech2@example.com", "王工程师", "机械维修,气动液压,焊接"),
        ("tech3@example.com", "赵工程师", "机器人维护,PLC编程"),
        ("tech4@example.com", "陈工程师", "电气维修,仪表校准"),
        ("tech5@example.com", "刘工程师", "机械维修,气动液压"),
    ]
    db.add_all([admin, sup])
    db.flush()
    techs: list[User] = []
    for email, name, skills in techs_data:
        u = User(email=email, hashed_password=hash_password(DEMO_PASSWORD), full_name=name, phone=f"1380000001{len(techs)+3}", role="technician")  # type: ignore[arg-type]
        db.add(u)
        db.flush()
        techs.append(u)
        profile = TechnicianProfile(user_id=u.id, employee_no=f"T{len(techs):03d}", availability="available", max_concurrent=5)
        db.add(profile)
        db.flush()
        for sn in skills.split(","):
            sk = db.query(Skill).filter(Skill.name == sn.strip()).first()
            if not sk:
                sk = Skill(name=sn.strip(), category="维修技能")
                db.add(sk)
                db.flush()
            profile.skills.append(sk)

    # 设备类型
    type_map: dict[str, EquipmentType] = {}
    for name, desc in EQUIPMENT_TYPES:
        t = EquipmentType(name=name, description=desc, created_by=str(admin.id))
        db.add(t)
        db.flush()
        type_map[name] = t

    # 故障代码
    fc_map: dict[str, FaultCode] = {}
    for code, name, sev, etype in FAULT_CODES:
        fc = FaultCode(code=code, name=name, severity=sev, equipment_type_id=type_map.get(etype).id if type_map.get(etype) else None)
        db.add(fc)
        db.flush()
        fc_map[code] = fc

    # 备件
    sp_map: dict[str, SparePart] = {}
    for code, name, spec, unit in SPARE_PARTS:
        sp = SparePart(code=code, name=name, specification=spec, unit=unit, stock_qty=random.randint(5, 50))
        db.add(sp)
        db.flush()
        sp_map[code] = sp

    # 设备 20 台
    import uuid

    PREFIX_MAP = {"数控机床": "CNC", "包装机": "PKG", "空压机": "AIR", "输送机": "CNV", "工业机器人": "RBT"}

    equipment_list: list[Equipment] = []
    eq_names = {
        "数控机床": ["CNC加工中心", "数控车床", "立式加工中心", "龙门加工中心", "数控铣床"],
        "包装机": ["全自动包装机", "立式包装机", "3号包装机", "颗粒包装机"],
        "空压机": ["螺杆空压机", "活塞空压机"],
        "输送机": ["滚筒输送线", "皮带输送机", "链板输送机"],
        "工业机器人": ["焊接机器人", "搬运机器人", "装配机器人"],
    }
    statuses_pool = [EquipmentStatusEnum.running] * 14 + [EquipmentStatusEnum.fault] * 3 + [EquipmentStatusEnum.under_repair] * 2 + [EquipmentStatusEnum.stopped] * 1
    eq_idx = 0
    for etype, names in eq_names.items():
        for i, n in enumerate(names):
            eq = Equipment(
                code=f"EQ-{PREFIX_MAP[etype]}{i+1:02d}",
                name=f"{n}",
                equipment_type_id=type_map[etype].id,
                plant=random.choice(PLANTS),
                production_line=random.choice(LINES),
                location=f"{random.choice(PLANTS)} {random.randint(1,3)}号车间",
                manufacturer=random.choice(["西门子", "三菱", "发那科", "ABB", "国产"]),
                model=f"Model-{etype[:2]}{i+100}",
                serial_number=f"SN{2024000+eq_idx}",
                commissioning_date=datetime(2021, random.randint(1, 12), random.randint(1, 28)).date(),
                status=statuses_pool[min(eq_idx, len(statuses_pool)-1)],
                risk_level=random.choice([RiskLevelEnum.low, RiskLevelEnum.medium, RiskLevelEnum.high]),
                responsible_person_id=random.choice(techs).id,
                qr_token=uuid.uuid4().hex,
                last_maintenance_at=(datetime.now(timezone.utc) - timedelta(days=random.randint(5, 90))).date(),
                created_by=str(admin.id),
            )
            db.add(eq)
            db.flush()
            equipment_list.append(eq)
            eq_idx += 1

    # 知识库
    for title, cat, content, tags, etype in KNOWLEDGE:
        art = KnowledgeArticle(
            title=title,
            category=cat,
            content=content,
            summary=content[:60],
            tags=tags,
            equipment_type_id=type_map[etype].id if etype in type_map else None,
            source="内部知识库",
            author_id=admin.id,
            status="published",
            created_by=str(admin.id),
        )
        db.add(art)
    db.flush()

    # 历史工单 30 条（已完成）
    wo_counter = 0
    for i in range(30):
        tpl, fcc, etype = random.choice(FAULT_TEMPLATES)
        eqs_of_type = [e for e in equipment_list if e.equipment_type_id == type_map[etype].id]
        if not eqs_of_type:
            continue
        eq = random.choice(eqs_of_type)
        tech = random.choice(techs)
        days_ago = random.randint(10, 180)
        created = datetime.now(timezone.utc) - timedelta(days=days_ago)
        start = created + timedelta(hours=random.randint(1, 8))
        end = start + timedelta(hours=random.randint(1, 12))
        wo_counter += 1
        wo = WorkOrder(
            code=_wo_code(db, wo_counter),
            title=f"{eq.name}{fcc}故障维修",
            equipment_id=eq.id,
            fault_description=tpl.format(eq=eq.name),
            fault_code_id=fc_map[fcc].id,
            order_type=WorkOrderTypeEnum.fault_repair,
            priority=random.choice(list(PriorityEnum)),
            status=WorkOrderStatusEnum.completed,
            created_by_id=sup.id,
            assignee_id=tech.id,
            actual_start_at=start,
            actual_end_at=end,
            planned_end_at=start + timedelta(hours=8),
            root_cause=ROOT_CAUSES[fcc],
            action_taken=ACTIONS[fcc],
            replaced_parts=PARTS_USED[fcc] or None,
            test_result="空载及负载测试通过，设备运行恢复正常",
            equipment_status_after="running",
            follow_up_advice="建议加强日常点检，关注该部位状态",
            needs_observation=random.choice([True, False]),
            safety_risk="执行了断电与上锁挂牌",
            created_by=str(sup.id),
            created_at=created,
        )
        db.add(wo)
        db.flush()
        db.add(WorkOrderAssignment(work_order_id=wo.id, assignee_id=tech.id, assigned_by=sup.id, assigned_at=created, is_current=False))
        db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=None, to_status="pending_dispatch", changed_by=sup.id, changed_at=created))
        # 维修记录
        db.add(MaintenanceLog(work_order_id=wo.id, log_type=MaintenanceLogTypeEnum.inspect, content=f"到达现场，确认设备 {eq.name} 故障现象，读取故障代码 {fcc}", operator_id=tech.id, operator_name=tech.full_name, logged_at=start))
        db.add(MaintenanceLog(work_order_id=wo.id, log_type=MaintenanceLogTypeEnum.repair, content=ACTIONS[fcc], operator_id=tech.id, operator_name=tech.full_name, logged_at=start + timedelta(hours=1)))
        db.add(MaintenanceLog(work_order_id=wo.id, log_type=MaintenanceLogTypeEnum.test, content="完成空载与负载测试，设备恢复正常", operator_id=tech.id, operator_name=tech.full_name, logged_at=end))
        # 工时
        db.add(LaborEntry(work_order_id=wo.id, started_at=start, ended_at=end, hours=round((end - start).total_seconds() / 3600, 1), is_downtime=random.choice([True, False]), operator_id=tech.id, operator_name=tech.full_name))
        # 备件
        if PARTS_USED[fcc]:
            db.add(WorkOrderSparePart(work_order_id=wo.id, spare_part_code=random.choice(list(sp_map.keys())), spare_part_name=random.choice(list(sp_map.values())).name, quantity=random.randint(1, 3), unit="个"))

    # 8 条未完成工单（各种状态）
    unfinished_statuses = [
        WorkOrderStatusEnum.pending_dispatch,
        WorkOrderStatusEnum.assigned,
        WorkOrderStatusEnum.accepted,
        WorkOrderStatusEnum.in_progress,
        WorkOrderStatusEnum.in_progress,
        WorkOrderStatusEnum.pending_acceptance,
        WorkOrderStatusEnum.returned,
        WorkOrderStatusEnum.paused,
    ]
    for i, st in enumerate(unfinished_statuses):
        tpl, fcc, etype = FAULT_TEMPLATES[i % len(FAULT_TEMPLATES)]
        eqs_of_type = [e for e in equipment_list if e.equipment_type_id == type_map[etype].id]
        if not eqs_of_type:
            eq = random.choice(equipment_list)
        else:
            eq = random.choice(eqs_of_type)
        tech = random.choice(techs)
        created = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 5))
        wo_counter += 1
        priority = PriorityEnum.P1 if i < 2 else random.choice([PriorityEnum.P2, PriorityEnum.P3])
        wo = WorkOrder(
            code=_wo_code(db, wo_counter),
            title=f"{eq.name}{fcc}故障维修",
            equipment_id=eq.id,
            fault_description=tpl.format(eq=eq.name),
            fault_code_id=fc_map[fcc].id,
            order_type=WorkOrderTypeEnum.fault_repair,
            priority=priority,
            status=st,
            created_by_id=sup.id,
            assignee_id=tech.id if st != WorkOrderStatusEnum.pending_dispatch else None,
            planned_end_at=datetime.now(timezone.utc) + timedelta(hours=random.randint(4, 48)),
            actual_start_at=datetime.now(timezone.utc) - timedelta(hours=2) if st in [WorkOrderStatusEnum.in_progress, WorkOrderStatusEnum.pending_acceptance, WorkOrderStatusEnum.returned, WorkOrderStatusEnum.paused] else None,
            safety_risk="涉及电气作业，维修前必须断电并执行 LOTO" if "E101" in fcc or "E102" in fcc else None,
            created_by=str(sup.id),
            created_at=created,
            # pending_acceptance 需要完工信息
            root_cause=ROOT_CAUSES[fcc] if st == WorkOrderStatusEnum.pending_acceptance else None,
            action_taken=ACTIONS[fcc] if st == WorkOrderStatusEnum.pending_acceptance else None,
            test_result="测试通过" if st == WorkOrderStatusEnum.pending_acceptance else None,
            equipment_status_after="running" if st == WorkOrderStatusEnum.pending_acceptance else None,
            rejection_reason="测试结果不明确，请补充负载测试数据" if st == WorkOrderStatusEnum.returned else None,
            submitted_at=datetime.now(timezone.utc) - timedelta(hours=1) if st == WorkOrderStatusEnum.pending_acceptance else None,
        )
        db.add(wo)
        db.flush()
        # 检查清单
        default_checklist = ["确认设备已停机", "执行断电操作", "执行上锁挂牌", "确认残余能量已释放", "读取故障代码", "检查相关部件", "执行维修", "恢复供电测试"]
        for j, content in enumerate(default_checklist):
            db.add(WorkOrderChecklistItem(work_order_id=wo.id, content=content, order=j, is_required=True, is_completed=st in [WorkOrderStatusEnum.in_progress, WorkOrderStatusEnum.pending_acceptance] and j < 4))
        db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=None, to_status="pending_dispatch", changed_by=sup.id, changed_at=created))
        if st != WorkOrderStatusEnum.pending_dispatch:
            db.add(MaintenanceLog(work_order_id=wo.id, log_type=MaintenanceLogTypeEnum.inspect, content=f"确认故障现象，读取故障代码 {fcc}", operator_id=tech.id, operator_name=tech.full_name, logged_at=datetime.now(timezone.utc) - timedelta(hours=3)))
        # 关联故障上报
        fr = FaultReport(
            equipment_id=eq.id,
            title=f"{eq.name}{fcc}故障",
            description=tpl.format(eq=eq.name),
            occurred_at=created,
            is_downtime="停机" in tpl or "无法" in tpl,
            affects_production="产线" in tpl,
            has_safety_risk="异响" in tpl,
            urgency=UrgencyEnum.high if priority == PriorityEnum.P1 else UrgencyEnum.medium,
            status=FaultReportStatusEnum.converted,
            reporter_name=random.choice(techs).full_name,
            created_by=str(sup.id),
            fault_code_id=fc_map[fcc].id,
        )
        db.add(fr)
        wo.fault_report_id = fr.id
