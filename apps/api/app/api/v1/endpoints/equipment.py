"""设备台账、设备类型、故障代码、备件接口。"""

from __future__ import annotations

import io

import qrcode
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, supervisor_or_admin
from app.core.exceptions import conflict, not_found, paginate
from app.db.session import get_db
from app.models.equipment import Equipment, EquipmentType, FaultCode, SparePart
from app.models.user import User
from app.schemas.common import PageOut
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentOut,
    EquipmentTypeCreate,
    EquipmentTypeOut,
    EquipmentUpdate,
    FaultCodeCreate,
    FaultCodeOut,
    SparePartCreate,
    SparePartOut,
)

router = APIRouter(prefix="/equipment", tags=["equipment"])


def _to_out(db: Session, eq: Equipment) -> EquipmentOut:
    type_name = None
    if eq.equipment_type_id:
        t = db.get(EquipmentType, eq.equipment_type_id)
        type_name = t.name if t else None
    resp_name = None
    if eq.responsible_person_id:
        u = db.get(User, eq.responsible_person_id)
        resp_name = u.full_name if u else None
    return EquipmentOut(
        id=eq.id,
        asset_uuid=eq.asset_uuid,
        code=eq.code,
        name=eq.name,
        equipment_type_id=eq.equipment_type_id,
        equipment_type_name=type_name,
        plant=eq.plant,
        production_line=eq.production_line,
        location=eq.location,
        manufacturer=eq.manufacturer,
        model=eq.model,
        serial_number=eq.serial_number,
        commissioning_date=eq.commissioning_date,
        status=eq.status,
        risk_level=eq.risk_level,
        health_score=eq.health_score,
        rated_parameters=eq.rated_parameters,
        cumulative_runtime_hours=eq.cumulative_runtime_hours,
        responsible_person_id=eq.responsible_person_id,
        responsible_person_name=resp_name,
        last_maintenance_at=eq.last_maintenance_at,
        next_maintenance_at=eq.next_maintenance_at,
        qr_token=eq.qr_token,
        remarks=eq.remarks,
        created_at=eq.created_at,
    )


@router.get("", response_model=PageOut[EquipmentOut])
def list_equipment(
    keyword: str | None = None,
    status: str | None = None,
    equipment_type_id: int | None = None,
    plant: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Equipment)
    if keyword:
        q = q.filter(
            Equipment.name.contains(keyword) | Equipment.code.contains(keyword)
        )
    if status:
        q = q.filter(Equipment.status == status)
    if equipment_type_id:
        q = q.filter(Equipment.equipment_type_id == equipment_type_id)
    if plant:
        q = q.filter(Equipment.plant == plant)
    items, total = paginate(q, page, page_size)
    return PageOut(
        items=[_to_out(db, e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=EquipmentOut)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    import uuid

    if db.query(Equipment).filter(Equipment.code == payload.code).first():
        raise conflict("设备编号已存在")
    eq = Equipment(
        **payload.model_dump(),
        qr_token=uuid.uuid4().hex,
        created_by=str(user.id),
    )
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return _to_out(db, eq)


@router.get("/{eq_id}", response_model=EquipmentOut)
def get_equipment(
    eq_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    eq = db.get(Equipment, eq_id)
    if not eq:
        raise not_found("设备不存在")
    return _to_out(db, eq)


@router.put("/{eq_id}", response_model=EquipmentOut)
def update_equipment(
    eq_id: int,
    payload: EquipmentUpdate,
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    eq = db.get(Equipment, eq_id)
    if not eq:
        raise not_found("设备不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(eq, k, v)
    eq.updated_by = str(user.id)
    db.commit()
    db.refresh(eq)
    return _to_out(db, eq)


@router.get("/{eq_id}/work-orders")
def equipment_work_orders(
    eq_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    from app.models.workorder import WorkOrder

    wos = (
        db.query(WorkOrder)
        .filter(WorkOrder.equipment_id == eq_id)
        .order_by(WorkOrder.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": w.id,
            "code": w.code,
            "title": w.title,
            "status": w.status.value,
            "priority": w.priority.value,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "root_cause": w.root_cause,
        }
        for w in wos
    ]


@router.get("/by-qr/{qr_token}", response_model=EquipmentOut)
def by_qr(qr_token: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    eq = db.query(Equipment).filter(Equipment.qr_token == qr_token).first()
    if not eq:
        raise not_found("二维码对应的设备不存在")
    return _to_out(db, eq)


@router.get("/{eq_id}/qrcode")
def equipment_qrcode(eq_id: int, db: Session = Depends(get_db)):
    eq = db.get(Equipment, eq_id)
    if not eq:
        raise not_found("设备不存在")
    url = f"equipment/{eq.id}?qr={eq.qr_token}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# ---------- 设备类型 ----------
types_router = APIRouter(prefix="/equipment-types", tags=["equipment"])


@types_router.get("", response_model=list[EquipmentTypeOut])
def list_types(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(EquipmentType).all()


@types_router.post("", response_model=EquipmentTypeOut)
def create_type(
    payload: EquipmentTypeCreate,
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    t = EquipmentType(**payload.model_dump(), created_by=str(user.id))
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ---------- 故障代码 ----------
fault_codes_router = APIRouter(prefix="/fault-codes", tags=["equipment"])


@fault_codes_router.get("", response_model=list[FaultCodeOut])
def list_fault_codes(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(FaultCode).all()


@fault_codes_router.post("", response_model=FaultCodeOut)
def create_fault_code(
    payload: FaultCodeCreate,
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    fc = FaultCode(**payload.model_dump())
    db.add(fc)
    db.commit()
    db.refresh(fc)
    return fc


# ---------- 备件 ----------
spare_parts_router = APIRouter(prefix="/spare-parts", tags=["equipment"])


@spare_parts_router.get("", response_model=list[SparePartOut])
def list_spare_parts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(SparePart).all()


@spare_parts_router.post("", response_model=SparePartOut)
def create_spare_part(
    payload: SparePartCreate,
    db: Session = Depends(get_db),
    user=Depends(supervisor_or_admin),
):
    sp = SparePart(**payload.model_dump())
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp
