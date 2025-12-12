import asyncio

import pytest

from services.worker_pool import WorkerPool, WorkerPriority


@pytest.mark.asyncio
async def test_slot_tasks_respect_priority() -> None:
    """[TC-WORKER-001] 슬롯 작업 우선순위 - HIGH가 NORMAL보다 먼저 실행된다.

    테스트 목적:
        동일 슬롯 큐에서 우선순위 HIGH 작업이 NORMAL 작업보다 먼저 소비되는지 확인한다.

    테스트 시나리오:
        Given: 슬롯 0에 NORMAL 작업과 HIGH 작업을 순서대로 enqueue 하고
        When: 워커 풀을 실행한 뒤 처리 순서를 기록하면
        Then: 결과 기록에서 HIGH가 NORMAL보다 먼저 나타난다

    Notes:
        None
    """
    results: list[str] = []

    async def record(name: str) -> None:
        results.append(name)

    pool = WorkerPool(slot_count=1, max_slot_queue_size=5)
    await pool.start()

    await pool.enqueue_slot(
        slot_idx=0,
        name="normal",
        coro_factory=lambda: record("normal"),
        priority=WorkerPriority.NORMAL,
    )
    await pool.enqueue_slot(
        slot_idx=0,
        name="high",
        coro_factory=lambda: record("high"),
        priority=WorkerPriority.HIGH,
    )

    await asyncio.sleep(0.05)
    await pool.stop()

    assert results[:2] == ["high", "normal"]


@pytest.mark.asyncio
async def test_top_worker_drops_when_full() -> None:
    """[TC-WORKER-002] Top 큐 포화 시 드랍 - drop_if_full 옵션을 따른다.

    테스트 목적:
        top 큐가 가득 찼을 때 drop_if_full=True 요청이 거부되고 False는 유지되는지 검증한다.

    테스트 시나리오:
        Given: max_top_queue_size=1 풀을 만들고 첫 번째 작업을 enqeue한 뒤
        When: 두 번째 작업을 drop_if_full=True로 enqueue 하면
        Then: 두 번째 enqueue는 False를 반환하고 실행된 리스트에는 첫 작업만 기록된다

    Notes:
        None
    """
    executed: list[str] = []

    async def record(name: str) -> None:
        executed.append(name)

    pool = WorkerPool(slot_count=1, max_top_queue_size=1)

    ok_first = await pool.enqueue_top(
        name="first",
        coro_factory=lambda: record("first"),
        drop_if_full=False,
    )
    ok_second = await pool.enqueue_top(
        name="second",
        coro_factory=lambda: record("second"),
        drop_if_full=True,
    )

    await pool.start()
    await asyncio.sleep(0.05)
    await pool.stop()

    assert ok_first is True
    assert ok_second is False
    assert "first" in executed
