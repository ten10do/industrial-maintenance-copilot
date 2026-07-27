"""Tests for fault report to work order conversion endpoint."""
import pytest
from sqlalchemy.orm import Session

from app.models.base import (
    FaultReportStatusEnum,
    PriorityEnum,
    UrgencyEnum,
    WorkOrderStatusEnum,
)
from app.models.fault import FaultReport
from app.models.workorder import WorkOrder, WorkOrderChecklistItem, WorkOrderStatusHistory


class TestConvertFaultReportToWorkOrder:
    """POST /fault-reports/{id}/convert-to-work-order"""

    # ---------- Success cases ----------

    def test_convert_success(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fault_report_id"] == fault_report_pending.id
        assert data["work_order_id"] is not None
        assert data["work_order_code"].startswith("WO-")
        assert data["priority"] == "P2"  # high urgency maps to P2

    def test_convert_copies_fields(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]

        wo = db.get(WorkOrder, wo_id)
        assert wo is not None
        assert wo.title == fault_report_pending.title
        assert wo.equipment_id == fault_report_pending.equipment_id
        assert wo.fault_description == fault_report_pending.description
        assert wo.fault_code_id == fault_report_pending.fault_code_id
        assert wo.fault_report_id == fault_report_pending.id
        assert wo.order_type.value == "fault_repair"

    def test_convert_maps_priority(self, client, auth_supervisor, db: Session, equipment, fault_code):
        test_cases = [
            (UrgencyEnum.critical, "P1"),
            (UrgencyEnum.high, "P2"),
            (UrgencyEnum.medium, "P3"),
            (UrgencyEnum.low, "P4"),
        ]
        for urgency, expected in test_cases:
            fr = FaultReport(
                equipment_id=equipment.id,
                title=f"Test {urgency.value}",
                description="Test",
                urgency=urgency,
                status=FaultReportStatusEnum.pending,
                is_downtime=False,
                affects_production=False,
                has_safety_risk=False,
                created_by="1",
            )
            db.add(fr)
            db.commit()
            db.refresh(fr)

            resp = client.post(
                f"/api/v1/fault-reports/{fr.id}/convert-to-work-order",
                headers=auth_supervisor,
                json={},
            )
            assert resp.status_code == 200
            assert resp.json()["priority"] == expected

    def test_user_can_override_priority(self, client, auth_supervisor, fault_report_pending):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={"priority": "P1"},
        )
        assert resp.status_code == 200
        assert resp.json()["priority"] == "P1"

    def test_safety_risk_enforces_minimum_priority(self, client, auth_supervisor, fault_report_critical):
        """Safety risk with P4 override should be promoted to at least P2."""
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_critical.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={"priority": "P4"},
        )
        assert resp.status_code == 200
        priority = resp.json()["priority"]
        assert priority in ("P1", "P2")

    def test_shutdown_and_production_impact_enforces_priority(self, client, auth_supervisor, db: Session, equipment, fault_code):
        fr = FaultReport(
            equipment_id=equipment.id,
            title="Shutdown test",
            description="Machine stopped, production halted",
            urgency=UrgencyEnum.medium,
            status=FaultReportStatusEnum.pending,
            is_downtime=True,
            affects_production=True,
            has_safety_risk=False,
            created_by="1",
        )
        db.add(fr)
        db.commit()
        db.refresh(fr)

        resp = client.post(
            f"/api/v1/fault-reports/{fr.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={"priority": "P4"},
        )
        assert resp.status_code == 200
        priority = resp.json()["priority"]
        assert priority in ("P1", "P2")

    def test_convert_updates_fault_report_status(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        db.refresh(fault_report_pending)
        assert fault_report_pending.status == FaultReportStatusEnum.converted

    def test_convert_creates_status_history(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]

        history = db.query(WorkOrderStatusHistory).filter(
            WorkOrderStatusHistory.work_order_id == wo_id
        ).all()
        assert len(history) >= 1
        assert history[0].to_status == WorkOrderStatusEnum.pending_dispatch.value

    def test_convert_creates_checklist(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]

        items = db.query(WorkOrderChecklistItem).filter(
            WorkOrderChecklistItem.work_order_id == wo_id
        ).all()
        assert len(items) > 0

    def test_admin_can_convert(self, client, auth_admin, fault_report_pending):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_admin,
            json={},
        )
        assert resp.status_code == 200

    def test_convert_with_notes(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={"notes": "请优先处理，生产任务紧急"},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]
        history = db.query(WorkOrderStatusHistory).filter(
            WorkOrderStatusHistory.work_order_id == wo_id
        ).first()
        assert history is not None
        assert "请优先处理" in (history.remark or "")

    # ---------- Permission / Error cases ----------

    def test_technician_cannot_convert(self, client, auth_technician, fault_report_pending):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_technician,
            json={},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_convert(self, client, fault_report_pending):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            json={},
        )
        assert resp.status_code == 401

    def test_missing_fault_report(self, client, auth_supervisor):
        resp = client.post(
            "/api/v1/fault-reports/99999/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 404

    def test_duplicate_conversion_returns_conflict(self, client, auth_supervisor, fault_report_pending, db: Session):
        # First conversion
        resp1 = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp1.status_code == 200
        wo_id = resp1.json()["work_order_id"]

        # Second conversion attempt
        resp2 = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp2.status_code == 409
        detail = resp2.json()["detail"]
        assert detail["code"] == "FAULT_REPORT_ALREADY_CONVERTED"
        assert detail["work_order_id"] == wo_id

    def test_closed_fault_report_cannot_convert(self, client, auth_supervisor, db: Session, equipment, fault_code):
        fr = FaultReport(
            equipment_id=equipment.id,
            title="Closed report",
            description="Already closed",
            urgency=UrgencyEnum.medium,
            status=FaultReportStatusEnum.closed,
            created_by="1",
        )
        db.add(fr)
        db.commit()
        db.refresh(fr)

        resp = client.post(
            f"/api/v1/fault-reports/{fr.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 400

    def test_converted_report_cannot_convert_again(self, client, auth_supervisor, db: Session, equipment, fault_code):
        fr = FaultReport(
            equipment_id=equipment.id,
            title="Already converted",
            description="Already converted",
            urgency=UrgencyEnum.medium,
            status=FaultReportStatusEnum.converted,
            created_by="1",
        )
        db.add(fr)
        db.commit()
        db.refresh(fr)

        # Pre-create a work order linked to this fault report
        wo = WorkOrder(
            code="WO-2026-TEST",
            title=fr.title,
            fault_report_id=fr.id,
            status=WorkOrderStatusEnum.pending_dispatch,
            created_by="1",
        )
        db.add(wo)
        db.commit()

        resp = client.post(
            f"/api/v1/fault-reports/{fr.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 409

    def test_convert_with_assignee(self, client, auth_supervisor, fault_report_pending, technician, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={"assignee_id": technician.id},
        )
        assert resp.status_code == 200
        # Note: assignee_id is captured in the response, actual assignment is not done here
        # since pending_dispatch is the initial state
        wo_id = resp.json()["work_order_id"]
        wo = db.get(WorkOrder, wo_id)
        assert wo is not None

    def test_convert_with_planned_dates(self, client, auth_supervisor, fault_report_pending, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_pending.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={
                "planned_start_at": "2026-07-28T08:00:00Z",
                "planned_end_at": "2026-07-28T17:00:00Z",
            },
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]
        wo = db.get(WorkOrder, wo_id)
        assert wo.planned_start_at is not None
        assert wo.planned_end_at is not None

    def test_safety_risk_flag_adds_safety_note(self, client, auth_supervisor, fault_report_critical, db: Session):
        resp = client.post(
            f"/api/v1/fault-reports/{fault_report_critical.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]
        wo = db.get(WorkOrder, wo_id)
        assert wo.safety_risk is not None
        assert "安全风险" in (wo.safety_risk or "")

    def test_high_risk_keywords_add_safety_note(self, client, auth_supervisor, db: Session, equipment, fault_code):
        fr = FaultReport(
            equipment_id=equipment.id,
            title="High voltage issue",
            description="高压设备异常",
            urgency=UrgencyEnum.high,
            status=FaultReportStatusEnum.pending,
            is_downtime=False,
            affects_production=False,
            has_safety_risk=False,
            created_by="1",
        )
        db.add(fr)
        db.commit()
        db.refresh(fr)

        resp = client.post(
            f"/api/v1/fault-reports/{fr.id}/convert-to-work-order",
            headers=auth_supervisor,
            json={},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["work_order_id"]
        wo = db.get(WorkOrder, wo_id)
        assert wo.safety_risk is not None
        assert "高危" in (wo.safety_risk or "")
