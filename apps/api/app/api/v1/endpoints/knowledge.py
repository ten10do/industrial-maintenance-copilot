"""知识库接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.knowledge_search import search_articles
from app.core.deps import get_current_user, supervisor_or_admin
from app.core.exceptions import not_found, paginate
from app.db.session import get_db
from app.models.knowledge import KnowledgeArticle
from app.schemas.common import OkResponse, PageOut
from app.schemas.knowledge import KnowledgeArticleCreate, KnowledgeArticleOut

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=PageOut[KnowledgeArticleOut])
def list_knowledge(
    keyword: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(KnowledgeArticle)
    if keyword:
        q = q.filter(KnowledgeArticle.title.contains(keyword) | KnowledgeArticle.content.contains(keyword))
    if category:
        q = q.filter(KnowledgeArticle.category == category)
    q = q.order_by(KnowledgeArticle.created_at.desc())
    items, total = paginate(q, page, page_size)
    return PageOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/search")
def search_knowledge(
    q: str = Query(..., min_length=1),
    fault_code: str | None = None,
    equipment_type_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return search_articles(db, q, equipment_type_id, fault_code, limit=8)


@router.get("/{k_id}", response_model=KnowledgeArticleOut)
def get_knowledge(k_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    art = db.get(KnowledgeArticle, k_id)
    if not art:
        raise not_found("知识条目不存在")
    art.view_count = (art.view_count or 0) + 1
    db.commit()
    db.refresh(art)
    return art


@router.post("", response_model=KnowledgeArticleOut)
def create_knowledge(payload: KnowledgeArticleCreate, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    art = KnowledgeArticle(**payload.model_dump(), author_id=user.id, created_by=str(user.id))
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


@router.put("/{k_id}", response_model=KnowledgeArticleOut)
def update_knowledge(k_id: int, payload: KnowledgeArticleCreate, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    art = db.get(KnowledgeArticle, k_id)
    if not art:
        raise not_found("知识条目不存在")
    for k, v in payload.model_dump().items():
        setattr(art, k, v)
    art.updated_by = str(user.id)
    db.commit()
    db.refresh(art)
    return art


@router.delete("/{k_id}", response_model=OkResponse)
def delete_knowledge(k_id: int, db: Session = Depends(get_db), user=Depends(supervisor_or_admin)):
    art = db.get(KnowledgeArticle, k_id)
    if not art:
        raise not_found("知识条目不存在")
    db.delete(art)
    db.commit()
    return OkResponse(message="知识条目已删除", id=k_id)
