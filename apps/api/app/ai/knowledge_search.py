"""知识库检索：基于关键词的全文检索（MVP 基线，向量不可用时自动降级到此）。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.equipment import FaultCode
from app.models.knowledge import KnowledgeArticle


def _tokenize(text: str) -> list[str]:
    # 中英混合分词：英文按词，中文按 2-gram
    if not text:
        return []
    tokens: list[str] = []
    for part in re.split(r"[\s,，。、；;:：！!？?()（）\[\]【】]+", text):
        if not part:
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]+", part):
            tokens.append(part.lower())
        else:
            for i in range(len(part) - 1):
                tokens.append(part[i : i + 2])
    return tokens


def search_articles(
    db: Session,
    query: str,
    equipment_type_id: int | None = None,
    fault_code: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """关键词检索知识文章，返回带得分的结果。"""
    q = db.query(KnowledgeArticle).filter(KnowledgeArticle.status == "published")
    tokens = _tokenize(query)
    results: list[dict[str, Any]] = []
    articles = q.all()
    # 故障代码映射
    fc_filter = None
    if fault_code:
        fc = db.query(FaultCode).filter(FaultCode.code == fault_code).first()
        if fc:
            fc_filter = fc.id
    for art in articles:
        if (
            equipment_type_id
            and art.equipment_type_id
            and art.equipment_type_id != equipment_type_id
        ):
            # 不强制过滤，只是降权
            pass
        haystack = " ".join(
            filter(
                None, [art.title, art.content, art.summary, " ".join(art.tags or [])]
            )
        )
        ht = _tokenize(haystack)
        if not tokens:
            score = 0.1
        else:
            score = sum(1 for t in tokens if t in ht) / max(len(tokens), 1)
        # 故障代码匹配加权
        if fc_filter and art.fault_code_id == fc_filter:
            score += 0.5
        if equipment_type_id and art.equipment_type_id == equipment_type_id:
            score += 0.2
        if score > 0:
            results.append(
                {
                    "article_id": art.id,
                    "title": art.title,
                    "content": art.content,
                    "summary": art.summary,
                    "category": art.category.value if art.category else None,
                    "source": art.source,
                    "score": round(score, 3),
                }
            )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def find_similar_work_orders(db, wo, limit: int = 3) -> list:
    """基于关键词相似度查找历史工单（向量降级方案）。"""
    from app.models.base import WorkOrderStatusEnum
    from app.models.workorder import WorkOrder

    base_text = " ".join(filter(None, [wo.title, wo.fault_description or ""]))
    tokens = set(_tokenize(base_text))
    candidates = (
        db.query(WorkOrder)
        .filter(WorkOrder.status == WorkOrderStatusEnum.completed)
        .filter(WorkOrder.id != wo.id)
        .limit(200)
        .all()
    )
    scored = []
    for c in candidates:
        ct = set(
            _tokenize(" ".join(filter(None, [c.title, c.fault_description or ""])))
        )
        if not tokens or not ct:
            continue
        overlap = len(tokens & ct) / max(len(tokens), 1)
        if overlap > 0.1:
            scored.append((c, overlap))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
