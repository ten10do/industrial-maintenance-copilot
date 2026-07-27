"""Copilot 高层能力：故障解析、诊断、润色、报告、问答、历史摘要。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.client import llm_client, record_ai_interaction
from app.ai.knowledge_search import find_similar_work_orders, search_articles
from app.models.base import UrgencyEnum
from app.models.equipment import Equipment, FaultCode
from app.models.workorder import WorkOrder
from app.schemas.fault import ParseFaultResult
from app.schemas.knowledge import (
    AskResult,
    DiagnoseResult,
    HistorySummary,
    MaintenanceReport,
    ReportSection,
    RewriteLogResult,
    SimilarCase,
)

DISCLAIMER = "AI 建议仅供辅助，维修人员应依据现场情况、设备手册和安全规范进行判断。"


# ---------------- 1. 自然语言故障解析 ----------------


def parse_fault(db: Session, text: str, user_id: int | None = None) -> ParseFaultResult:
    result = ParseFaultResult(description=text, raw={"text": text})

    if llm_client.enabled:
        prompt = _build_parse_prompt(db, text)
        resp = llm_client.chat(prompt, json_mode=True)
        if resp["content"]:
            data = llm_client.parse_json(resp["content"])
            if data:
                result = _coerce_parse(data, text)
                record_ai_interaction(
                    db, user_id, "parse_fault", text, resp["content"], resp["is_mock"], resp["model"], resp.get("latency_ms", 0), resp["error"]
                )
                return result
        # AI 失败则降级到规则解析
        record_ai_interaction(db, user_id, "parse_fault", text, None, True, resp["model"], 0, resp["error"])

    # 规则解析（Mock / 降级）
    parsed = _rule_based_parse(db, text)
    record_ai_interaction(db, user_id, "parse_fault", text, str(parsed.dict()), True, "mock")
    return parsed


def _build_parse_prompt(db: Session, text: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "你是工业设备故障解析助手。从用户输入的自然语言中提取结构化故障信息，"
                "返回 JSON，字段：title, description, equipment_keyword, phenomenon, "
                "fault_code, is_downtime(bool), affects_production(bool), has_safety_risk(bool), "
                "urgency(low/medium/high/critical), suggested_priority(P1-P4), confidence(0-1)。"
                "只返回 JSON，不要额外解释。"
            ),
        },
        {"role": "user", "content": text},
    ]


def _coerce_parse(data: dict, text: str) -> ParseFaultResult:
    urgency = data.get("urgency", "medium")
    try:
        urgency = UrgencyEnum(urgency)
    except ValueError:
        urgency = UrgencyEnum.medium
    return ParseFaultResult(
        title=data.get("title"),
        description=data.get("description", text),
        equipment_keyword=data.get("equipment_keyword"),
        phenomenon=data.get("phenomenon"),
        fault_code=data.get("fault_code"),
        is_downtime=bool(data.get("is_downtime", False)),
        affects_production=bool(data.get("affects_production", False)),
        has_safety_risk=bool(data.get("has_safety_risk", False)),
        urgency=urgency,
        suggested_priority=data.get("suggested_priority"),
        confidence=float(data.get("confidence", 0.5)),
        raw=data,
    )


def _rule_based_parse(db: Session, text: str) -> ParseFaultResult:
    lower = text.lower()
    # 故障代码 E1xx / E2xx
    fc_match = re.search(r"[Ee](\d{2,4})", text)
    fault_code = f"E{fc_match.group(1)}" if fc_match else None
    # 停机
    is_downtime = any(k in text for k in ["停机", "停了", "无法运行", "不能启动", "停止"])
    affects_production = any(k in text for k in ["整条", "产线", "生产线", "影响生产", "停工"])
    has_safety_risk = any(k in text for k in ["异响", "冒烟", "漏电", "火花", "高温", "泄漏", "爆炸"])
    urgency = UrgencyEnum.critical if (is_downtime and affects_production) else UrgencyEnum.high if has_safety_risk else UrgencyEnum.medium
    priority = "P1" if urgency == UrgencyEnum.critical else "P2" if urgency == UrgencyEnum.high else "P3"
    # 设备关键词
    eq_keyword = None
    for kw in ["包装机", "空压机", "数控机床", "输送机", "机器人", "冲床", "注塑机", "电机", "控制柜"]:
        if kw in text:
            eq_keyword = kw
            break
    # 匹配设备编号
    eq_match = re.search(r"(\d+)\s*号", text)
    title = f"{eq_keyword or '设备'}故障" + (f"-E{fc_match.group(1)}" if fc_match else "")
    return ParseFaultResult(
        title=title,
        description=text,
        equipment_keyword=eq_keyword,
        phenomenon=eq_keyword + (" 异常" if eq_keyword else " 故障"),
        fault_code=fault_code,
        is_downtime=is_downtime,
        affects_production=affects_production,
        has_safety_risk=has_safety_risk,
        urgency=urgency,
        suggested_priority=priority,
        confidence=0.6,
        raw={"method": "rule"},
    )


# ---------------- 2. AI 辅助诊断 ----------------


def diagnose(db: Session, fault_description: str, equipment_id: int | None, fault_code: str | None, wo: WorkOrder | None, user_id: int | None = None) -> DiagnoseResult:
    # 相似历史工单
    similar: list[SimilarCase] = []
    if wo:
        for c, score in find_similar_work_orders(db, wo, limit=3):
            similar.append(SimilarCase(work_order_id=c.id, code=c.code, title=c.title, similarity=round(score, 2), root_cause=c.root_cause, action_taken=c.action_taken))

    if llm_client.enabled:
        prompt = _build_diagnose_prompt(db, fault_description, equipment_id, fault_code, similar)
        resp = llm_client.chat(prompt, json_mode=True)
        if resp["content"]:
            data = llm_client.parse_json(resp["content"])
            if data:
                result = DiagnoseResult(
                    possible_causes=data.get("possible_causes", []),
                    inspection_order=data.get("inspection_order", []),
                    safety_notes=data.get("safety_notes", []),
                    recommended_tools=data.get("recommended_tools", []),
                    recommended_parts=data.get("recommended_parts", []),
                    similar_cases=similar,
                    is_mock=False,
                )
                record_ai_interaction(db, user_id, "diagnose", fault_description, resp["content"], False, resp["model"], resp.get("latency_ms", 0))
                return result
        record_ai_interaction(db, user_id, "diagnose", fault_description, None, True, resp["model"], 0, resp["error"])

    # Mock 规则诊断
    result = _mock_diagnose(fault_description, fault_code, similar)
    record_ai_interaction(db, user_id, "diagnose", fault_description, result.model_dump_json(), True, "mock")
    return result


def _build_diagnose_prompt(db, fault_description, equipment_id, fault_code, similar) -> list[dict]:
    eq_info = ""
    if equipment_id:
        eq = db.get(Equipment, equipment_id)
        if eq:
            eq_info = f"设备：{eq.name}({eq.code})，制造商：{eq.manufacturer}，型号：{eq.model}"
    return [
        {
            "role": "system",
            "content": (
                "你是工业设备维修诊断专家。根据故障描述给出结构化 JSON："
                "possible_causes(数组,每项含cause与confidence), inspection_order(字符串数组),"
                "safety_notes(字符串数组), recommended_tools(字符串数组), recommended_parts(字符串数组)。"
                "严禁建议绕过安全装置、带电拆卸或绕过联锁。只返回 JSON。"
            ),
        },
        {"role": "user", "content": f"{eq_info}\n故障代码：{fault_code or '未知'}\n故障描述：{fault_description}"},
    ]


def _mock_diagnose(fault_description: str, fault_code: str | None, similar: list[SimilarCase]) -> DiagnoseResult:
    text = fault_description or ""
    causes = []
    if fault_code:
        causes.append({"cause": f"{fault_code} 故障代码相关传感器或驱动异常", "confidence": 0.7})
    if "异响" in text:
        causes.append({"cause": "机械部件松动或轴承磨损导致异响", "confidence": 0.65})
    if "温度" in text or "过热" in text:
        causes.append({"cause": "散热不良或负载过载导致温升", "confidence": 0.6})
    if "气压" in text or "压力" in text:
        causes.append({"cause": "气路泄漏或过滤器堵塞导致压力不足", "confidence": 0.6})
    if "跑偏" in text:
        causes.append({"cause": "输送带张力不均或导轮磨损导致跑偏", "confidence": 0.7})
    if not causes:
        causes.append({"cause": "控制信号异常或传感器故障", "confidence": 0.5})
    safety = ["维修前必须执行断电与上锁挂牌（LOTO）", "确认残余能量已释放", "佩戴相应劳保用品"]
    if "电" in text or "控制柜" in text:
        safety.append("电气作业需由持证电工执行，使用绝缘工具")
    if "高温" in text or "过热" in text:
        safety.append("等待设备冷却后再接触，防止烫伤")
    return DiagnoseResult(
        possible_causes=causes,
        inspection_order=["确认设备已停机并断电", "执行上锁挂牌", "读取并记录故障代码", "检查相关传感器与线路", "检查机械连接与润滑", "必要时更换部件", "恢复供电并测试"],
        safety_notes=safety,
        recommended_tools=["万用表", "绝缘手套", "扭矩扳手", "内六角套装"],
        recommended_parts=["接近开关", "保险丝", "继电器"],
        similar_cases=similar,
        is_mock=True,
    )


# ---------------- 3. 维修记录润色 ----------------


def rewrite_log(db: Session, content: str, user_id: int | None = None) -> RewriteLogResult:
    if llm_client.enabled:
        prompt = [
            {"role": "system", "content": "你是维修记录规范化助手。将口语化维修记录改写为规范、专业、客观的记录，保留关键事实，不要添加臆测内容。只输出改写后的文本。"},
            {"role": "user", "content": content},
        ]
        resp = llm_client.chat(prompt)
        if resp["content"]:
            record_ai_interaction(db, user_id, "rewrite_log", content, resp["content"], False, resp["model"], resp.get("latency_ms", 0))
            return RewriteLogResult(original=content, polished=resp["content"], is_mock=False)
        record_ai_interaction(db, user_id, "rewrite_log", content, None, True, resp["model"], 0, resp["error"])
    polished = _mock_rewrite(content)
    record_ai_interaction(db, user_id, "rewrite_log", content, polished, True, "mock")
    return RewriteLogResult(original=content, polished=polished, is_mock=True)


def _mock_rewrite(content: str) -> str:
    c = content.strip()
    if "松了" in c:
        c = c.replace("松了", "安装松动")
    if "查了下" in c:
        c = c.replace("查了下", "经检查")
    if "重新固定" in c:
        c = c.replace("重新固定", "已重新紧固")
    if "测试正常" in c:
        c = c.replace("测试正常", "空载及负载测试均正常，设备运行恢复")
    prefix = "经检查，" if not c.startswith("经检查") else ""
    suffix = "" if c.endswith("。") else "。"
    return f"{prefix}{c}{suffix}"


# ---------------- 4. 自动生成完工报告 ----------------


def generate_report(db: Session, wo_id: int, user_id: int | None = None) -> MaintenanceReport:
    wo = db.get(WorkOrder, wo_id)
    if not wo:
        return MaintenanceReport(work_order_id=wo_id, work_order_code="", summary="工单不存在", is_mock=True)
    eq_name = ""
    if wo.equipment_id:
        eq = db.get(Equipment, wo.equipment_id)
        if eq:
            eq_name = f"{eq.name}({eq.code})"

    sections = [
        ReportSection(title="故障概述", content=f"{wo.title}。{wo.fault_description or ''}".strip()),
        ReportSection(title="影响范围", content=f"设备：{eq_name}。停机影响：{'是' if wo.safety_risk else '否'}。"),
        ReportSection(title="根本原因", content=wo.root_cause or "未记录"),
        ReportSection(title="维修措施", content=wo.action_taken or "未记录"),
        ReportSection(title="更换部件", content=wo.replaced_parts or "无"),
        ReportSection(title="测试结果", content=wo.test_result or "未记录"),
        ReportSection(title="安全措施", content=wo.safety_risk or "执行了断电与上锁挂牌"),
        ReportSection(title="后续建议", content=wo.follow_up_advice or "建议持续观察设备运行状态"),
    ]
    summary = f"工单 {wo.code} 已完成。设备 {eq_name} 故障原因为「{wo.root_cause or '未知'}」，已执行「{wo.action_taken or '维修'}」，测试结果：{wo.test_result or '正常'}。"

    if llm_client.enabled:
        prompt = _build_report_prompt(wo, eq_name, sections)
        resp = llm_client.chat(prompt, json_mode=True)
        if resp["content"]:
            data = llm_client.parse_json(resp["content"])
            if data and "sections" in data:
                sections = [ReportSection(title=s.get("title", ""), content=s.get("content", "")) for s in data["sections"]]
                summary = data.get("summary", summary)
                record_ai_interaction(db, user_id, "generate_report", str(wo_id), resp["content"], False, resp["model"], resp.get("latency_ms", 0))
                return MaintenanceReport(work_order_id=wo.id, work_order_code=wo.code, sections=sections, summary=summary, is_mock=False)
        record_ai_interaction(db, user_id, "generate_report", str(wo_id), None, True, resp["model"], 0, resp["error"])

    record_ai_interaction(db, user_id, "generate_report", str(wo_id), summary, True, "mock")
    return MaintenanceReport(work_order_id=wo.id, work_order_code=wo.code, sections=sections, summary=summary, is_mock=True)


def _build_report_prompt(wo, eq_name, sections) -> list[dict]:
    base = "\n".join(f"{s.title}: {s.content}" for s in sections)
    return [
        {"role": "system", "content": "你是维修报告生成助手。根据工单数据生成结构化维修报告 JSON，包含 sections(数组,每项含title和content) 与 summary 字段。客观严谨，不要编造数据。只返回 JSON。"},
        {"role": "user", "content": f"工单号：{wo.code}\n设备：{eq_name}\n基础数据：\n{base}"},
    ]


# ---------------- 5. 知识库问答 ----------------


def ask(db: Session, question: str, equipment_type_id: int | None, fault_code: str | None, user_id: int | None = None) -> AskResult:
    sources = search_articles(db, question, equipment_type_id, fault_code, limit=5)
    kb_context = "\n\n".join([f"【{s['title']}】(来源:{s['source'] or '内部知识库'}, 得分:{s['score']})\n{s['content'][:800]}" for s in sources])

    if llm_client.enabled and sources:
        prompt = [
            {"role": "system", "content": "你是维修知识问答助手。优先依据提供的知识库内容回答，引用来源。不确定时明确说明。严禁伪造设备手册内容。"},
            {"role": "user", "content": f"知识库参考：\n{kb_context}\n\n问题：{question}"},
        ]
        resp = llm_client.chat(prompt)
        if resp["content"]:
            record_ai_interaction(db, user_id, "ask", question, resp["content"], False, resp["model"], resp.get("latency_ms", 0))
            return AskResult(answer=resp["content"], sources=sources, is_mock=False)
        record_ai_interaction(db, user_id, "ask", question, None, True, resp["model"], 0, resp["error"])

    # Mock：基于检索结果拼接
    if sources:
        top = sources[0]
        answer = f"根据知识库「{top['title']}」：\n{top['content'][:500]}\n\n建议结合现场情况判断。"
    else:
        answer = "知识库中未检索到直接相关内容。建议查阅设备手册或联系资深工程师，AI 不可替代现场专业判断。"
    record_ai_interaction(db, user_id, "ask", question, answer, True, "mock")
    return AskResult(answer=answer, sources=sources, is_mock=True)


# ---------------- 6. 历史工单摘要 ----------------


def history_summary(db: Session, equipment_id: int) -> HistorySummary:
    eq = db.get(Equipment, equipment_id)
    if not eq:
        return HistorySummary(equipment_id=equipment_id, equipment_name="", total_work_orders=0, is_mock=True)
    wos = db.query(WorkOrder).filter(WorkOrder.equipment_id == equipment_id).order_by(WorkOrder.created_at.desc()).all()
    total = len(wos)
    # 高频故障
    fault_count: dict[str, int] = {}
    for w in wos:
        key = w.fault_description or w.title
        fault_count[key] = fault_count.get(key, 0) + 1
    frequent = [{"fault": k, "count": v} for k, v in sorted(fault_count.items(), key=lambda x: -x[1])[:5]]
    recent = [{"code": w.code, "title": w.title, "status": w.status.value, "created_at": w.created_at.isoformat() if w.created_at else None} for w in wos[:5]]
    repeated = [{"fault": k, "count": v} for k, v in fault_count.items() if v >= 2][:3]
    # 常见更换部件
    parts: dict[str, int] = {}
    hours_list = []
    for w in wos:
        if w.replaced_parts:
            for p in re.split(r"[,，、\n]+", w.replaced_parts):
                p = p.strip()
                if p:
                    parts[p] = parts.get(p, 0) + 1
        if w.actual_start_at and w.actual_end_at:
            delta = (w.actual_end_at - w.actual_start_at).total_seconds() / 3600
            if delta > 0:
                hours_list.append(delta)
    common_parts = [{"part": k, "count": v} for k, v in sorted(parts.items(), key=lambda x: -x[1])[:5]]
    avg_hours = round(sum(hours_list) / len(hours_list), 1) if hours_list else None
    return HistorySummary(
        equipment_id=equipment_id,
        equipment_name=f"{eq.name}({eq.code})",
        total_work_orders=total,
        frequent_faults=frequent,
        recent_faults=recent,
        repeated_faults=repeated,
        common_parts=common_parts,
        avg_repair_hours=avg_hours,
        is_mock=True,
    )
