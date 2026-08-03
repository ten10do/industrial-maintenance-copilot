"""AI 客户端：OpenAI 兼容接口适配层，含 Mock 降级。"""

from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import Any, Protocol

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings


class LLMClient:
    """统一的 LLM 调用入口。AI 不可用时返回 Mock 结果。"""

    def __init__(self) -> None:
        self.enabled = settings.ai_actually_enabled
        self.model = settings.LLM_MODEL or "mock-model"
        self.api_base = settings.LLM_API_BASE.rstrip("/")
        self.api_key = settings.LLM_API_KEY
        self.timeout = settings.AI_REQUEST_TIMEOUT_SECONDS

    @property
    def is_mock(self) -> bool:
        return not self.enabled

    def chat(
        self, messages: list[dict[str, Any]], json_mode: bool = False
    ) -> dict[str, Any]:
        """返回 {'content': str, 'is_mock': bool, 'model': str, 'error': str|None}。"""
        if not self.enabled:
            return {
                "content": "",
                "is_mock": True,
                "model": "mock",
                "error": None,
            }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            start = time.time()
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.api_base}/chat/completions", headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            latency = int((time.time() - start) * 1000)
            return {
                "content": content,
                "is_mock": False,
                "model": self.model,
                "error": None,
                "latency_ms": latency,
            }
        except Exception as e:  # 降级
            return {
                "content": "",
                "is_mock": True,
                "model": self.model,
                "error": str(e),
            }

    def parse_json(self, content: str) -> dict[str, Any] | None:
        """安全解析模型返回的 JSON。"""
        if not content:
            return None
        try:
            return json.loads(content)
        except Exception:
            # 尝试提取代码块中的 JSON
            import re

            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
            return None


class LLMProvider(Protocol):
    enabled: bool
    model: str

    def chat(
        self, messages: list[dict[str, Any]], json_mode: bool = False
    ) -> dict[str, Any]: ...

    def parse_json(self, content: str) -> dict[str, Any] | None: ...


llm_client: LLMProvider = LLMClient()


def record_ai_interaction(
    db,
    user_id: int | None,
    interaction_type: str,
    request: str,
    response: str | None,
    is_mock: bool,
    model: str | None = None,
    latency_ms: int = 0,
    error: str | None = None,
) -> None:
    """记录 AI 调用状态。不抛异常以免影响主流程。"""
    try:
        from app.models.base import AIInteractionTypeEnum, AIStatusEnum
        from app.models.knowledge import AIInteraction

        try:
            itype = AIInteractionTypeEnum(interaction_type)
        except ValueError:
            itype = AIInteractionTypeEnum.ask  # type: ignore[assignment]
        status = (
            AIStatusEnum.mock
            if is_mock
            else (AIStatusEnum.failed if error else AIStatusEnum.success)
        )
        rec = AIInteraction(
            user_id=user_id,
            interaction_type=itype,
            request=request,
            response=response,
            status=status,
            model=model,
            latency_ms=latency_ms,
            error=error,
        )
        db.add(rec)
        db.commit()
    except SQLAlchemyError:
        with suppress(SQLAlchemyError):
            db.rollback()
