"""Trace Context 单元测试：创建 / 复用 / 嵌套 / async 隔离 / 无全局泄漏。"""

from __future__ import annotations

import asyncio

from app.core.trace import (
    _context,
    bind_trace,
    current_context,
    current_trace_id,
    new_trace_id,
    start_trace,
    trace_attributes,
)


def test_start_trace_creates_new_id() -> None:
    ctx = start_trace("unit-test")
    assert current_context() is ctx
    assert len(ctx.trace_id) == 36
    assert ctx.source == "unit-test"
    assert ctx.request_id is None


def test_trace_ids_are_unique() -> None:
    assert new_trace_id() != new_trace_id()


def test_bind_trace_reuses_existing_id() -> None:
    existing = new_trace_id()
    ctx = bind_trace(existing, source="alarm-analyze")
    assert ctx.trace_id == existing
    assert current_trace_id() == existing
    assert ctx.source == "alarm-analyze"


def test_bind_trace_without_id_generates_and_warns() -> None:
    ctx = bind_trace(None, source="fallback")
    assert len(ctx.trace_id) == 36
    assert current_trace_id() == ctx.trace_id


def test_request_id_independent_of_trace_id() -> None:
    ctx = start_trace("http", request_id="req-123")
    assert ctx.request_id == "req-123"
    assert ctx.trace_id != "req-123"
    attrs = trace_attributes()
    assert attrs["request_id"] == "req-123"
    assert attrs["trace_id"] == ctx.trace_id


def test_nested_bind_restores_outer_on_token_reset() -> None:
    outer = start_trace("outer")
    from app.core.trace import TraceContext

    # 直接 set 一个新的内部上下文以精确控制 token 语义
    token = _context.set(TraceContext(trace_id=new_trace_id(), source="inner"))
    try:
        assert current_trace_id() != outer.trace_id
    finally:
        _context.reset(token)
    assert current_trace_id() == outer.trace_id


def test_no_global_leak_between_sequential_starts() -> None:
    first = start_trace("first")
    second = start_trace("second")
    assert first.trace_id != second.trace_id
    assert current_trace_id() == second.trace_id


def test_asyncio_child_bind_does_not_leak_to_parent() -> None:
    """子任务内的 bind_trace 不得污染父上下文（contextvars 副本语义）。"""
    trace_a, trace_b = new_trace_id(), new_trace_id()

    async def main() -> dict[str, str | None]:
        root = start_trace("root")
        seen: dict[str, str | None] = {}

        async def worker(name: str, override: str) -> None:
            await asyncio.sleep(0.01)
            bind_trace(override, source=name)
            seen[name] = current_trace_id()

        await asyncio.gather(worker("a", trace_a), worker("b", trace_b))
        seen["parent"] = current_trace_id()
        assert seen["parent"] == root.trace_id
        return seen

    seen = asyncio.run(main())
    assert seen["a"] == trace_a
    assert seen["b"] == trace_b
    assert seen["a"] != seen["b"]
    # 父级未被任何子任务覆盖
    assert seen["parent"] not in {trace_a, trace_b}


def test_concurrent_ingress_tasks_get_isolated_traces() -> None:
    """两个并发入口各自 start_trace：互不可见、互不串写。"""

    async def main() -> dict[str, str]:
        seen: dict[str, str] = {}

        async def ingress(name: str) -> None:
            await asyncio.sleep(0.005 * (name == "slow"))
            ctx = start_trace(f"ingress-{name}")
            await asyncio.sleep(0.02)
            # 第二次读取必须仍是自己的 trace（不被并发入口覆盖）
            assert current_trace_id() == ctx.trace_id
            seen[name] = ctx.trace_id

        await asyncio.gather(ingress("fast"), ingress("slow"))
        return seen

    seen = asyncio.run(main())
    assert seen["fast"] != seen["slow"]
