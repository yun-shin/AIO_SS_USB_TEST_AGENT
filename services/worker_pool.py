"""Worker pool for Agent.

비동기 워커를 역할별로 분리해 백엔드 응답 우선순위와 슬롯 단위 직렬화를
보장한다. Top(worker0)은 백엔드 응답 전용, Scheduler(worker1)은 슬롯 단위
락/큐 관리, Slot worker(worker1-x)는 슬롯별 작업을 순차 처리한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Awaitable, Callable, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


class WorkerPriority(IntEnum):
    """작업 우선순위 (낮은 숫자가 높은 우선순위)."""

    IMMEDIATE = 0
    HIGH = 5
    NORMAL = 10
    LOW = 20


@dataclass(order=True)
class WorkerItem:
    """큐에 적재되는 공통 작업."""

    priority: int
    seq: int
    name: str = field(compare=False)
    coro_factory: Callable[[], Awaitable[object]] = field(compare=False)
    drop_if_full: bool = field(compare=False, default=False)


@dataclass(order=True)
class SlotTask(WorkerItem):
    """슬롯 지정 작업."""

    slot_idx: int = field(compare=False, default=0)


class _QueueWorker:
    """우선순위 큐 기반 워커."""

    def __init__(
        self,
        name: str,
        max_queue_size: int,
        logger_name: str,
    ) -> None:
        self._name = name
        self._queue: asyncio.PriorityQueue[WorkerItem] = asyncio.PriorityQueue(
            max_queue_size
        )
        self._logger = get_logger(logger_name)
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """워크 루프 시작."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        self._logger.info("Worker started", worker=self._name)

    async def stop(self) -> None:
        """워크 루프 정지."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._logger.info("Worker stopped", worker=self._name)

    async def enqueue(
        self,
        item: WorkerItem,
    ) -> bool:
        """작업 적재."""
        if item.drop_if_full:
            try:
                self._queue.put_nowait(item)
            except asyncio.QueueFull:
                self._logger.warning(
                    "Queue full - drop task",
                    worker=self._name,
                    task=item.name,
                )
                return False
        else:
            await self._queue.put(item)
        return True

    async def _run(self) -> None:
        """큐를 소비하며 작업 실행."""
        try:
            while self._running:
                item = await self._queue.get()
                try:
                    await item.coro_factory()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - 로깅 목적
                    self._logger.error(
                        "Worker task failed",
                        worker=self._name,
                        task=item.name,
                        error=str(exc),
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            pass


class WorkerPool:
    """에이전트 워커 풀.

    - Top worker: 백엔드 응답/로그 전송 최우선 처리
    - Scheduler worker: 슬롯별 경합 방지 및 작업 전달
    - Slot workers: 슬롯 단위 직렬 실행
    """

    def __init__(
        self,
        slot_count: int,
        max_top_queue_size: int = 200,
        max_slot_queue_size: int = 50,
    ) -> None:
        self._slot_count = slot_count
        self._top_worker = _QueueWorker(
            name="top",
            max_queue_size=max_top_queue_size,
            logger_name="worker_top",
        )
        self._slot_workers: dict[int, _QueueWorker] = {
            idx: _QueueWorker(
                name=f"slot-{idx}",
                max_queue_size=max_slot_queue_size,
                logger_name=f"worker_slot_{idx}",
            )
            for idx in range(slot_count)
        }
        self._scheduler_queue: asyncio.PriorityQueue[SlotTask] = asyncio.PriorityQueue(
            max_slot_queue_size * slot_count
        )
        self._scheduler_task: Optional[asyncio.Task] = None
        self._seq = 0
        self._running = False

    async def start(self) -> None:
        """모든 워커 시작."""
        if self._running:
            return
        self._running = True
        await self._top_worker.start()
        for worker in self._slot_workers.values():
            await worker.start()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Worker pool started", slot_count=self._slot_count)

    async def stop(self) -> None:
        """모든 워커 정지."""
        self._running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._scheduler_task = None

        await self._top_worker.stop()
        for worker in self._slot_workers.values():
            await worker.stop()
        logger.info("Worker pool stopped")

    async def enqueue_top(
        self,
        name: str,
        coro_factory: Callable[[], Awaitable[object]],
        priority: WorkerPriority = WorkerPriority.IMMEDIATE,
        drop_if_full: bool = False,
    ) -> bool:
        """Top(worker0)에 작업 적재."""
        item = WorkerItem(
            priority=int(priority),
            seq=self._next_seq(),
            name=name,
            coro_factory=coro_factory,
            drop_if_full=drop_if_full,
        )
        return await self._top_worker.enqueue(item)

    async def enqueue_slot(
        self,
        slot_idx: int,
        name: str,
        coro_factory: Callable[[], Awaitable[object]],
        priority: WorkerPriority = WorkerPriority.NORMAL,
        drop_if_full: bool = False,
    ) -> bool:
        """Scheduler(worker1)에 슬롯 작업 적재."""
        if slot_idx not in self._slot_workers:
            logger.error("Invalid slot index for worker", slot_idx=slot_idx)
            return False

        task = SlotTask(
            priority=int(priority),
            seq=self._next_seq(),
            slot_idx=slot_idx,
            name=name,
            coro_factory=coro_factory,
            drop_if_full=drop_if_full,
        )

        if task.drop_if_full:
            try:
                self._scheduler_queue.put_nowait(task)
            except asyncio.QueueFull:
                logger.warning(
                    "Scheduler queue full - drop task",
                    slot_idx=slot_idx,
                    task=name,
                )
                return False
        else:
            await self._scheduler_queue.put(task)

        return True

    async def _scheduler_loop(self) -> None:
        """Scheduler(worker1) 루프."""
        try:
            while self._running:
                task = await self._scheduler_queue.get()
                worker = self._slot_workers.get(task.slot_idx)
                if not worker:
                    self._scheduler_queue.task_done()
                    continue

                scheduled = await worker.enqueue(task)
                if not scheduled:
                    logger.warning(
                        "Failed to enqueue task to slot worker",
                        slot_idx=task.slot_idx,
                        task=task.name,
                    )
                self._scheduler_queue.task_done()
        except asyncio.CancelledError:
            pass

    def _next_seq(self) -> int:
        """단조 증가 시퀀스."""
        self._seq += 1
        return self._seq
