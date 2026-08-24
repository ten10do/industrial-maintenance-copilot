"""测试维修执行完整生命周期：检查清单、日志、工时、备件、完工、验收、报告。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.base import (
    EquipmentStatusEnum,
    FaultReportStatusEnum,
    KnowledgeCategoryEnum,
    MaintenanceLogTypeEnum,
    WorkOrderStatusEnum,
)
from app.models.equipment import Equipment
from app.models.fault import FaultReport
from app.models.knowledge import AcceptanceRecord, KnowledgeArticle
from app.models.maintenance import (
    LaborEntry,
    MaintenanceLog,
    WorkOrderReport,
    WorkOrderSparePart,
)
from app.models.workorder import (
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderChecklistItem,
    WorkOrderStatusHistory,
)
from app.schemas.knowledge import MaintenanceReport, ReportSection


def _make_wo(db, **kw):
    """Helper: create and flush a WorkOrder to DB."""
    code = kw.pop("code", f"WO-TEST-{datetime.now(UTC).microsecond}")
    wo = WorkOrder(code=code, title="测试工单", created_by_id=1, **kw)
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


class TestWorkOrderAdministration:
    def test_technician_cannot_create_work_order(
        self, client, auth_technician, equipment
    ):
        res = client.post(
            "/api/v1/work-orders",
            json={"title": "越权创建", "equipment_id": equipment.id},
            headers=auth_technician,
        )
        assert res.status_code == 403

    def test_manual_creation_records_initial_status(
        self, client, auth_supervisor, db, supervisor, equipment
    ):
        res = client.post(
            "/api/v1/work-orders",
            json={"title": "手工创建历史", "equipment_id": equipment.id},
            headers=auth_supervisor,
        )

        assert res.status_code == 200
        history = (
            db.query(WorkOrderStatusHistory)
            .filter(WorkOrderStatusHistory.work_order_id == res.json()["id"])
            .one()
        )
        assert history.from_status is None
        assert history.to_status == WorkOrderStatusEnum.pending_dispatch.value
        assert history.changed_by == supervisor.id

    def test_reassignment_keeps_exactly_one_current_assignment(
        self,
        client,
        auth_supervisor,
        db,
        technician,
        another_technician,
        equipment,
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.pending_dispatch,
        )

        first = client.post(
            f"/api/v1/work-orders/{wo.id}/assign",
            json={"assignee_id": technician.id},
            headers=auth_supervisor,
        )
        second = client.post(
            f"/api/v1/work-orders/{wo.id}/assign",
            json={"assignee_id": another_technician.id},
            headers=auth_supervisor,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assignments = (
            db.query(WorkOrderAssignment)
            .filter(WorkOrderAssignment.work_order_id == wo.id)
            .order_by(WorkOrderAssignment.id)
            .all()
        )
        assert len(assignments) == 2
        assert assignments[0].is_current is False
        assert assignments[1].is_current is True
        assert assignments[1].assignee_id == another_technician.id
        assigned_transitions = (
            db.query(WorkOrderStatusHistory)
            .filter(
                WorkOrderStatusHistory.work_order_id == wo.id,
                WorkOrderStatusHistory.to_status == WorkOrderStatusEnum.assigned.value,
            )
            .count()
        )
        assert assigned_transitions == 1


class TestWorkOrderStartRepair:
    """开始维修测试 — 需要先接受工单"""

    @staticmethod
    def _make_high_risk_work_order(db, equipment, technician, *, completed: bool):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.accepted,
            assignee_id=technician.id,
            safety_risk="高压电气设备，开始维修前必须执行 LOTO",
        )
        now = datetime.now(UTC)
        for order, content in enumerate(["设备已停机", "已执行上锁挂牌（LOTO）"]):
            db.add(
                WorkOrderChecklistItem(
                    work_order_id=wo.id,
                    category="safety",
                    content=content,
                    order=order,
                    is_required=True,
                    is_completed=completed,
                    completed_by=technician.id if completed else None,
                    completed_at=now if completed else None,
                )
            )
        db.commit()
        db.refresh(wo)
        return wo

    def test_start_repair_success(
        self, client, auth_technician, db, technician, equipment
    ):
        """被分派的工程师接受工单后可以开始维修。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.assigned,
            assignee_id=technician.id,
        )
        # 先接受
        client.post(f"/api/v1/work-orders/{wo.id}/accept", headers=auth_technician)
        db.refresh(wo)

        res = client.post(f"/api/v1/work-orders/{wo.id}/start", headers=auth_technician)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "in_progress"
        assert data["actual_start_at"] is not None

    def test_non_assignee_cannot_start(
        self, client, auth_technician, db, supervisor, equipment
    ):
        """非被分派工程师不能接受和开始维修。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.assigned,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/accept", headers=auth_technician
        )
        assert res.status_code == 403

    def test_invalid_status_cannot_start(
        self, client, auth_technician, db, technician, equipment
    ):
        """非法状态下不能开始维修（必须先接受）。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.pending_dispatch,
            assignee_id=technician.id,
        )

        res = client.post(f"/api/v1/work-orders/{wo.id}/start", headers=auth_technician)
        assert res.status_code == 400

    def test_non_assignee_cannot_pause(
        self, client, auth_technician, db, supervisor, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/pause",
            headers=auth_technician,
        )

        assert res.status_code == 403

    def test_start_creates_status_history(
        self, client, auth_technician, db, technician, equipment
    ):
        """开始维修记录状态历史。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.assigned,
            assignee_id=technician.id,
        )
        client.post(f"/api/v1/work-orders/{wo.id}/accept", headers=auth_technician)
        db.refresh(wo)

        res = client.post(f"/api/v1/work-orders/{wo.id}/start", headers=auth_technician)
        assert res.status_code == 200
        history = (
            db.query(WorkOrderStatusHistory)
            .filter(WorkOrderStatusHistory.work_order_id == wo.id)
            .all()
        )
        assert len(history) >= 2  # assigned→accepted + accepted→in_progress
        assert any(h.to_status == "in_progress" for h in history)

    def test_high_risk_start_rejects_missing_confirmation(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = self._make_high_risk_work_order(db, equipment, technician, completed=True)

        res = client.post(f"/api/v1/work-orders/{wo.id}/start", headers=auth_technician)

        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "HIGH_RISK_SAFETY_CONFIRMATION_REQUIRED"
        db.refresh(wo)
        assert wo.status == WorkOrderStatusEnum.accepted

    def test_high_risk_start_rejects_incomplete_safety_checklist(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = self._make_high_risk_work_order(db, equipment, technician, completed=False)

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/start",
            json={"confirmed": True, "note": "已核对现场隔离和防护措施"},
            headers=auth_technician,
        )

        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["code"] == "HIGH_RISK_SAFETY_CHECKLIST_INCOMPLETE"
        assert detail["missing_items"] == ["设备已停机", "已执行上锁挂牌（LOTO）"]

    def test_high_risk_start_records_atomic_safety_confirmation(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = self._make_high_risk_work_order(db, equipment, technician, completed=True)
        note = "已核对现场隔离、LOTO 和个人防护措施"

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/start",
            json={"confirmed": True, "note": note},
            headers=auth_technician,
        )

        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"
        history = (
            db.query(WorkOrderStatusHistory)
            .filter(
                WorkOrderStatusHistory.work_order_id == wo.id,
                WorkOrderStatusHistory.to_status
                == WorkOrderStatusEnum.in_progress.value,
            )
            .one()
        )
        assert history.changed_by == technician.id
        assert history.changed_at is not None
        assert history.remark == f"高风险作业安全确认：{note}"

    def test_high_risk_resume_requires_new_confirmation(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = self._make_high_risk_work_order(db, equipment, technician, completed=True)
        wo.status = WorkOrderStatusEnum.paused
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/resume", headers=auth_technician
        )

        assert res.status_code == 422
        assert res.json()["detail"]["code"] == "HIGH_RISK_SAFETY_CONFIRMATION_REQUIRED"


class TestChecklistItems:
    """检查清单测试"""

    def test_complete_checklist_item(
        self, client, auth_technician, db, technician, equipment
    ):
        """完成检查清单项。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )
        # 手动添加检查项
        item = WorkOrderChecklistItem(
            work_order_id=wo.id,
            category="safety",
            content="设备已停机",
            order=0,
            is_required=True,
            is_completed=False,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        res = client.put(
            f"/api/v1/work-orders/{wo.id}/checklist/{item.id}",
            json={"is_completed": True},
            headers=auth_technician,
        )
        assert res.status_code == 200
        # 验证数据库
        db.refresh(item)
        assert item.is_completed is True
        assert item.completed_at is not None

    def test_non_assignee_cannot_complete_checklist(
        self, client, auth_technician, db, supervisor, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )
        item = WorkOrderChecklistItem(
            work_order_id=wo.id,
            category="repair",
            content="执行维修",
            order=0,
            is_required=True,
        )
        db.add(item)
        db.commit()

        res = client.put(
            f"/api/v1/work-orders/{wo.id}/checklist/{item.id}",
            json={"is_completed": True},
            headers=auth_technician,
        )

        assert res.status_code == 403

    def test_checklist_has_categories(self, client, auth_supervisor, db, equipment):
        """新创建的工单检查项应有类别。"""
        payload = {
            "title": "类别测试",
            "equipment_id": equipment.id,
            "fault_description": "测试",
        }
        res = client.post("/api/v1/work-orders", json=payload, headers=auth_supervisor)
        assert res.status_code == 200
        items = res.json()["checklist_items"]
        categories = {c["category"] for c in items}
        for expected in ["safety", "diagnosis", "repair", "testing"]:
            assert expected in categories

    def test_safety_items_are_required(self, client, auth_supervisor, db, equipment):
        """安全检查项应为必做。"""
        payload = {
            "title": "安全测试",
            "equipment_id": equipment.id,
            "fault_description": "测试",
        }
        res = client.post("/api/v1/work-orders", json=payload, headers=auth_supervisor)
        assert res.status_code == 200
        safety_items = [
            c for c in res.json()["checklist_items"] if c["category"] == "safety"
        ]
        assert all(c["is_required"] for c in safety_items)
        assert len(safety_items) == 7


class TestMaintenanceLogs:
    """维修日志测试"""

    def test_add_maintenance_log(
        self, client, auth_technician, db, technician, equipment
    ):
        """添加维修日志。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/logs",
            json={"log_type": "repair", "content": "更换了主轴轴承"},
            headers=auth_technician,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["log_type"] == "repair"
        assert data["content"] == "更换了主轴轴承"
        assert data["operator_id"] == technician.id

    def test_add_log_preserves_raw_content(
        self, client, auth_technician, db, technician, equipment
    ):
        """添加日志保存原始内容。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/logs",
            json={
                "log_type": "diagnose",
                "content": "经诊断，轴承磨损严重",
                "raw_content": "查看了下，坏了",
            },
            headers=auth_technician,
        )
        assert res.status_code == 200
        assert res.json()["raw_content"] == "查看了下，坏了"

    def test_completed_wo_cannot_add_log(
        self, client, auth_technician, db, technician, equipment
    ):
        """已完成工单不能添加日志。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.completed,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/logs",
            json={"log_type": "note", "content": "不应成功"},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_non_assignee_cannot_add_log(
        self, client, auth_technician, db, supervisor, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/logs",
            json={"log_type": "note", "content": "越权记录"},
            headers=auth_technician,
        )

        assert res.status_code == 403

    def test_assigned_work_order_cannot_add_log(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.assigned,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/logs",
            json={"log_type": "note", "content": "尚未接单"},
            headers=auth_technician,
        )

        assert res.status_code == 400


class TestLaborEntries:
    """工时记录测试"""

    def test_add_valid_labor(self, client, auth_technician, db, technician, equipment):
        """添加有效工时。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={"hours": 2.5, "is_downtime": True, "remark": "更换轴承"},
            headers=auth_technician,
        )
        assert res.status_code == 200
        assert res.json()["hours"] == 2.5
        assert res.json()["is_downtime"] is True

    def test_reject_zero_hours(
        self, client, auth_technician, db, technician, equipment
    ):
        """拒绝零工时。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={"hours": 0},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_reject_negative_hours(
        self, client, auth_technician, db, technician, equipment
    ):
        """拒绝负工时。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={"hours": -1},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_reject_invalid_time_range(
        self, client, auth_technician, db, technician, equipment
    ):
        """拒绝结束时间早于开始时间。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={
                "hours": 1,
                "started_at": "2026-01-02T10:00:00",
                "ended_at": "2026-01-02T09:00:00",
            },
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_completed_wo_cannot_add_labor(
        self, client, auth_technician, db, technician, equipment
    ):
        """已完成工单不能添加工时。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.completed,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={"hours": 1},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_non_assignee_cannot_add_labor(
        self, client, auth_technician, db, supervisor, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/labor",
            json={"hours": 1},
            headers=auth_technician,
        )

        assert res.status_code == 403


class TestSpareParts:
    """备件使用测试"""

    def test_add_valid_spare_part(
        self, client, auth_technician, db, technician, equipment
    ):
        """添加有效备件。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/spare-parts",
            json={"spare_part_name": "轴承 6205", "quantity": 2, "unit": "个"},
            headers=auth_technician,
        )
        assert res.status_code == 200
        assert res.json()["spare_part_name"] == "轴承 6205"
        assert res.json()["quantity"] == 2

    def test_reject_zero_quantity(
        self, client, auth_technician, db, technician, equipment
    ):
        """拒绝零数量备件。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/spare-parts",
            json={"spare_part_name": "测试", "quantity": 0},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_reject_negative_quantity(
        self, client, auth_technician, db, technician, equipment
    ):
        """拒绝负数备件。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/spare-parts",
            json={"spare_part_name": "测试", "quantity": -1},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_completed_wo_cannot_add_spare(
        self, client, auth_technician, db, technician, equipment
    ):
        """已完成工单不能添加备件。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.completed,
            assignee_id=technician.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/spare-parts",
            json={"spare_part_name": "测试", "quantity": 1},
            headers=auth_technician,
        )
        assert res.status_code == 400

    def test_non_assignee_cannot_add_spare(
        self, client, auth_technician, db, supervisor, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/spare-parts",
            json={"spare_part_name": "越权备件", "quantity": 1},
            headers=auth_technician,
        )

        assert res.status_code == 403

    def test_update_rejects_non_positive_quantity(
        self, client, auth_technician, db, technician, equipment
    ):
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
        )
        record = WorkOrderSparePart(
            work_order_id=wo.id,
            spare_part_name="轴承",
            quantity=1,
            unit="个",
        )
        db.add(record)
        db.commit()

        res = client.put(
            f"/api/v1/work-orders/{wo.id}/spare-parts/{record.id}",
            json={"quantity": 0},
            headers=auth_technician,
        )

        assert res.status_code == 422


class TestWorkOrderCompletion:
    """完工提交测试"""

    def _make_ready_wo(self, client, db, equipment, technician):
        """创建准备就绪的工单（in_progress + 全部检查项完成 + 日志 + 工时）。"""
        wo = WorkOrder(
            code=f"WO-SUB-{datetime.now(UTC).microsecond}",
            title="提交测试",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
        )
        db.add(wo)
        db.flush()
        # 检查项：safety + testing 全部完成
        for i, (cat, content, req) in enumerate(
            [
                ("safety", "设备已停机", True),
                ("safety", "已断电", True),
                ("diagnosis", "检查故障", True),
                ("repair", "执行维修", True),
                ("testing", "空载测试", True),
                ("testing", "负载测试", True),
            ]
        ):
            db.add(
                WorkOrderChecklistItem(
                    work_order_id=wo.id,
                    category=cat,
                    content=content,
                    order=i,
                    is_required=req,
                    is_completed=True,
                    completed_at=datetime.now(UTC),
                )
            )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="更换轴承",
                operator_id=technician.id,
                logged_at=datetime.now(UTC),
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=2.0, operator_id=technician.id))
        db.commit()
        db.refresh(wo)
        return wo

    def test_submit_completion_success(
        self, client, auth_technician, db, technician, equipment
    ):
        """满足条件后提交完工成功。"""
        wo = self._make_ready_wo(client, db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={
                "root_cause": "轴承疲劳磨损",
                "action_taken": "更换 6205 轴承",
                "test_result": "空载运行正常，负载测试通过",
            },
            headers=auth_technician,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "pending_acceptance"
        assert data["root_cause"] == "轴承疲劳磨损"
        assert data["submitted_at"] is not None

    def test_submit_rejected_missing_root_cause(
        self, client, auth_technician, db, technician, equipment
    ):
        """缺少根本原因时拒绝提交。"""
        wo = self._make_ready_wo(client, db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={
                "root_cause": "",
                "action_taken": "���处理",
                "test_result": "测试通过",
            },
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "missing_requirements" in res.json()
        assert "root_cause" in res.json()["missing_requirements"]

    def test_submit_rejected_missing_log(
        self, client, auth_technician, db, technician, equipment
    ):
        """缺少维修日志时拒绝提交。"""
        wo = WorkOrder(
            code="WO-NOLOG",
            title="无日志",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
        )
        db.add(wo)
        db.flush()
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="safety",
                content="安全",
                order=0,
                is_required=True,
                is_completed=True,
            )
        )
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="testing",
                content="测试",
                order=1,
                is_required=True,
                is_completed=True,
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=1.0))
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={"root_cause": "测试", "action_taken": "测试", "test_result": "测试"},
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "maintenance_log" in res.json()["missing_requirements"]

    def test_submit_rejected_missing_required_checklist(
        self, client, auth_technician, db, technician, equipment
    ):
        """缺少必做检查项时拒绝提交。"""
        wo = WorkOrder(
            code="WO-NOCHK",
            title="无检查",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
        )
        db.add(wo)
        db.flush()
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="safety",
                content="未完成",
                order=0,
                is_required=True,
                is_completed=False,
            )
        )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="维修",
                operator_id=technician.id,
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=1.0))
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={"root_cause": "测试", "action_taken": "测试", "test_result": "测试"},
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "required_checklist_items" in res.json()["missing_requirements"]

    def test_submit_rejected_missing_labor(
        self, client, auth_technician, db, technician, equipment
    ):
        """缺少工时记录时拒绝提交。"""
        wo = WorkOrder(
            code="WO-NOLAB",
            title="无工时",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
        )
        db.add(wo)
        db.flush()
        for i, (cat, content) in enumerate([("safety", "安全"), ("testing", "测试")]):
            db.add(
                WorkOrderChecklistItem(
                    work_order_id=wo.id,
                    category=cat,
                    content=content,
                    order=i,
                    is_required=True,
                    is_completed=True,
                )
            )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="维修",
                operator_id=technician.id,
            )
        )
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={"root_cause": "测试", "action_taken": "测试", "test_result": "测试"},
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "labor_entry" in res.json()["missing_requirements"]

    def test_submit_rejected_missing_test_step(
        self, client, auth_technician, db, technician, equipment
    ):
        """缺少测试步骤时拒绝提交。"""
        wo = WorkOrder(
            code="WO-NOTEST",
            title="无测试",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
        )
        db.add(wo)
        db.flush()
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="safety",
                content="安全",
                order=0,
                is_required=True,
                is_completed=True,
            )
        )
        db.add(
            WorkOrderChecklistItem(
                work_order_id=wo.id,
                category="testing",
                content="负载测试",
                order=1,
                is_required=True,
                is_completed=False,
            )
        )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="维修",
                operator_id=technician.id,
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=1.0))
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={"root_cause": "测试", "action_taken": "测试", "test_result": "测试"},
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "test_step" in res.json()["missing_requirements"]

    def test_high_risk_wo_requires_photo(
        self, client, auth_technician, db, technician, equipment
    ):
        """高风险工单需要完工照片。"""
        wo = WorkOrder(
            code="WO-HIRISK",
            title="高压故障",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
            safety_risk="高压电气设备",
            fault_description="高压漏电",
        )
        db.add(wo)
        db.flush()
        for i, (cat, content) in enumerate([("safety", "安全"), ("testing", "测试")]):
            db.add(
                WorkOrderChecklistItem(
                    work_order_id=wo.id,
                    category=cat,
                    content=content,
                    order=i,
                    is_required=True,
                    is_completed=True,
                )
            )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="维修",
                operator_id=technician.id,
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=1.0))
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={
                "root_cause": "绝缘老化",
                "action_taken": "更换绝缘层",
                "test_result": "测试通过",
                "completion_photos": [],
            },
            headers=auth_technician,
        )
        assert res.status_code == 422
        assert "completion_photo" in res.json()["missing_requirements"]

    def test_high_risk_resubmit_preserves_existing_photo(
        self, client, auth_technician, db, technician, equipment
    ):
        """返工后重新提交时可以复用已经上传的完工照片。"""
        existing_photo = "/api/v1/files/workorders/existing.png"
        wo = WorkOrder(
            code="WO-HIRISK-RESUBMIT",
            title="高压故障返工",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=technician.id,
            created_by_id=technician.id,
            safety_risk="高压电气设备",
            completion_photos=[existing_photo],
        )
        db.add(wo)
        db.flush()
        for i, (category, content) in enumerate(
            [("safety", "安全"), ("testing", "测试")]
        ):
            db.add(
                WorkOrderChecklistItem(
                    work_order_id=wo.id,
                    category=category,
                    content=content,
                    order=i,
                    is_required=True,
                    is_completed=True,
                )
            )
        db.add(
            MaintenanceLog(
                work_order_id=wo.id,
                log_type=MaintenanceLogTypeEnum.repair,
                content="维修",
                operator_id=technician.id,
            )
        )
        db.add(LaborEntry(work_order_id=wo.id, hours=1.0))
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={
                "root_cause": "绝缘老化",
                "action_taken": "更换绝缘层",
                "test_result": "测试通过",
            },
            headers=auth_technician,
        )

        assert res.status_code == 200
        db.refresh(wo)
        assert wo.completion_photos == [existing_photo]

    def test_non_assignee_cannot_submit(
        self, client, auth_technician, db, equipment, supervisor
    ):
        """非负责人不能提交完工。"""
        wo = _make_wo(
            db,
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.in_progress,
            assignee_id=supervisor.id,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={"root_cause": "测试", "action_taken": "测试", "test_result": "测试"},
            headers=auth_technician,
        )
        assert res.status_code == 403

    def test_submit_changes_status_to_pending_acceptance(
        self, client, auth_technician, db, technician, equipment
    ):
        """提交后状态变为 pending_acceptance。"""
        wo = self._make_ready_wo(client, db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/submit",
            json={
                "root_cause": "轴承损坏",
                "action_taken": "更换",
                "test_result": "通过",
            },
            headers=auth_technician,
        )
        assert res.status_code == 200
        db.refresh(wo)
        assert wo.status == WorkOrderStatusEnum.pending_acceptance


class TestWorkOrderAcceptance:
    """主管验收测试"""

    def _make_pending_wo(self, db, equipment, technician):
        """创建待验收工单。"""
        wo = WorkOrder(
            code=f"WO-APP-{datetime.now(UTC).microsecond}",
            title="验收测试",
            equipment_id=equipment.id,
            status=WorkOrderStatusEnum.pending_acceptance,
            assignee_id=technician.id,
            created_by_id=technician.id,
            root_cause="轴承磨损",
            action_taken="更换轴承",
            test_result="测试通过",
        )
        db.add(wo)
        db.commit()
        db.refresh(wo)
        return wo

    def test_supervisor_approve_success(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """主管验收通过。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["actual_end_at"] is not None

    def test_technician_cannot_approve(
        self, client, auth_technician, db, equipment, technician
    ):
        """工程师不能验收。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_technician
        )
        assert res.status_code == 403

    def test_reject_requires_remark(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """退回时必须填写原因。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/reject",
            json={"remark": ""},
            headers=auth_supervisor,
        )
        assert res.status_code == 400

    def test_reject_success(self, client, auth_supervisor, db, equipment, technician):
        """验收退回成功。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/reject",
            json={"remark": "测试结果不充分"},
            headers=auth_supervisor,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "returned"
        assert data["rejection_reason"] == "测试结果不充分"

    def test_acceptance_updates_equipment_status(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收更新设备状态为运行中。"""
        wo = self._make_pending_wo(db, equipment, technician)
        # 设置设备为故障状态
        eq = db.get(Equipment, equipment.id)
        eq.status = EquipmentStatusEnum.fault
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        db.refresh(eq)
        assert eq.status == EquipmentStatusEnum.running
        assert eq.last_maintenance_at is not None

    def test_acceptance_creates_acceptance_record(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收通过创建验收记录。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        record = (
            db.query(AcceptanceRecord)
            .filter(AcceptanceRecord.work_order_id == wo.id)
            .first()
        )
        assert record is not None
        assert record.result == "approved"

    def test_reject_creates_acceptance_record(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """退回创建验收记录。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/reject",
            json={"remark": "需要补充"},
            headers=auth_supervisor,
        )
        assert res.status_code == 200
        record = (
            db.query(AcceptanceRecord)
            .filter(AcceptanceRecord.work_order_id == wo.id)
            .first()
        )
        assert record is not None
        assert record.result == "rejected"

    def test_double_approve_returns_conflict(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """重复验收返回冲突。"""
        wo = self._make_pending_wo(db, equipment, technician)
        client.post(f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 409
        assert res.json()["code"] == "WORK_ORDER_ALREADY_ACCEPTED"

    def test_acceptance_closes_fault_report(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收关闭来源故障上报。"""
        fr = FaultReport(
            title="验收测试故障",
            description="故障描述",
            status=FaultReportStatusEnum.pending,
            created_by="1",
        )
        db.add(fr)
        db.flush()
        wo = WorkOrder(
            code="WO-CLOSE-FR",
            title="验收-关故障",
            equipment_id=equipment.id,
            fault_report_id=fr.id,
            status=WorkOrderStatusEnum.pending_acceptance,
            assignee_id=technician.id,
            created_by_id=technician.id,
            root_cause="测试",
            action_taken="测试",
            test_result="测试",
        )
        db.add(wo)
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        db.refresh(fr)
        assert fr.status == FaultReportStatusEnum.closed

    def test_acceptance_generates_report(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收生成维修报告。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        report = (
            db.query(WorkOrderReport)
            .filter(
                WorkOrderReport.work_order_id == wo.id,
                WorkOrderReport.is_current == True,  # noqa: E712
            )
            .first()
        )
        assert report is not None
        assert len(report.summary) > 0

    def test_acceptance_uses_template_when_ai_generation_raises(
        self,
        client,
        auth_supervisor,
        db,
        equipment,
        technician,
        monkeypatch,
    ):
        wo = self._make_pending_wo(db, equipment, technician)
        calls: list[bool] = []

        def fake_generate_report(_db, wo_id, _user_id=None, force_template=False):
            calls.append(force_template)
            if not force_template:
                raise RuntimeError("AI unavailable")
            return MaintenanceReport(
                work_order_id=wo_id,
                work_order_code=wo.code,
                summary="模板报告",
                sections=[ReportSection(title="结果", content="已完成")],
                is_mock=True,
            )

        monkeypatch.setattr(
            "app.api.v1.endpoints.work_orders.ai_generate_report",
            fake_generate_report,
        )

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve",
            headers=auth_supervisor,
        )

        assert res.status_code == 200
        assert calls == [False, True]
        report = (
            db.query(WorkOrderReport)
            .filter(WorkOrderReport.work_order_id == wo.id)
            .one()
        )
        assert report.generation_method == "template"

    def test_acceptance_generates_knowledge_candidate(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收生成知识库候选条目。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        article = (
            db.query(KnowledgeArticle)
            .filter(KnowledgeArticle.source == f"work_order_{wo.id}")
            .first()
        )
        assert article is not None
        assert article.status == "draft"
        assert article.category == KnowledgeCategoryEnum.case

    def test_knowledge_candidate_no_duplicate(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """同一工单只生成一个候选。"""
        wo = self._make_pending_wo(db, equipment, technician)
        db.add(
            KnowledgeArticle(
                title="已有",
                content="已有",
                source=f"work_order_{wo.id}",
                status="draft",
            )
        )
        db.commit()

        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        count = (
            db.query(KnowledgeArticle)
            .filter(KnowledgeArticle.source == f"work_order_{wo.id}")
            .count()
        )
        assert count == 1

    def test_reject_allows_re_edit(
        self, client, auth_supervisor, auth_technician, db, equipment, technician
    ):
        """退回后工单可继续编辑（重新开始维修）。"""
        wo = self._make_pending_wo(db, equipment, technician)
        client.post(
            f"/api/v1/work-orders/{wo.id}/reject",
            json={"remark": "不完整"},
            headers=auth_supervisor,
        )
        # 工程师重新开始
        res = client.post(f"/api/v1/work-orders/{wo.id}/start", headers=auth_technician)
        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"

    def test_report_generation_without_ai(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """AI 不可用时使用模板生成报告。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        report = (
            db.query(WorkOrderReport)
            .filter(
                WorkOrderReport.work_order_id == wo.id,
                WorkOrderReport.is_current == True,  # noqa: E712
            )
            .first()
        )
        assert report is not None
        assert report.generation_method == "template"

    def test_get_report_for_completed_wo(
        self, client, auth_supervisor, auth_technician, db, equipment, technician
    ):
        """已完成工单可获取只读报告。"""
        wo = self._make_pending_wo(db, equipment, technician)
        client.post(f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor)

        res = client.get(f"/api/v1/work-orders/{wo.id}/report", headers=auth_technician)
        assert res.status_code == 200
        report = res.json()
        assert report["work_order_id"] == wo.id
        assert "summary" in report

    def test_approve_records_status_history(
        self, client, auth_supervisor, db, equipment, technician
    ):
        """验收后状态历史记录完整。"""
        wo = self._make_pending_wo(db, equipment, technician)
        res = client.post(
            f"/api/v1/work-orders/{wo.id}/approve", headers=auth_supervisor
        )
        assert res.status_code == 200
        histories = (
            db.query(WorkOrderStatusHistory)
            .filter(WorkOrderStatusHistory.work_order_id == wo.id)
            .order_by(WorkOrderStatusHistory.changed_at)
            .all()
        )
        assert any(h.to_status == "completed" for h in histories)
