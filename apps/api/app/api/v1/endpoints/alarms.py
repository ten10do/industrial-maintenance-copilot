"""工业报警 API：查看与人工确认（acknowledge）。

报警由 OPC UA DataChange / Alarm 事件流水线产生（只读采集的派生记录）；
确认操作只修改平台内的报警记录，不向设备写入任何内容。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.industrial_gateway.models import IndustrialAlarm
from app.industrial_gateway.schemas import IndustrialAlarmOut
from app.models.user import User

router = APIRouter(prefix="/alarms", tags=["industrial-alarms"])


@router.get("")
def list_alarms(
    status: str | None = Query(default=None, description="active|acknowledged|cleared"),
    equipment_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    """查看工业报警列表（severity / equipment / timestamp / status）。"""
    query = db.query(IndustrialAlarm)
    if status == "active":
        query = query.filter(IndustrialAlarm.cleared_at.is_(None))
    elif status == "cleared":
        query = query.filter(IndustrialAlarm.cleared_at.is_not(None))
    elif status == "acknowledged":
        query = query.filter(IndustrialAlarm.acknowledged.is_(True))
    if equipment_id is not None:
        query = query.filter(IndustrialAlarm.equipment_id == equipment_id)
    total = query.count()
    rows = query.order_by(IndustrialAlarm.created_at.desc()).limit(limit).all()
    return {
        "items": [IndustrialAlarmOut.model_validate(row) for row in rows],
        "total": total,
        "read_only_source": True,
    }


@router.post("/{alarm_id}/acknowledge")
def acknowledge_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(supervisor_or_admin),
) -> dict[str, object]:
    """人工确认报警（平台内记录，不触碰设备）。"""
    alarm = db.get(IndustrialAlarm, alarm_id)
    if alarm is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="工业报警不存在")
    if not alarm.acknowledged:
        alarm.acknowledged = True
        alarm.acknowledged_at = datetime.now(UTC)
        alarm.acknowledged_by = user.id
        db.commit()
        db.refresh(alarm)
    return {
        "ok": True,
        "id": alarm.id,
        "acknowledged": alarm.acknowledged,
        "acknowledged_at": alarm.acknowledged_at.isoformat()
        if alarm.acknowledged_at
        else None,
    }
