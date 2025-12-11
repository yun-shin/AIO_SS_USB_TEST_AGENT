"""Batch Executor Service.

Service responsible for executing multi-iteration batch tests.
Orchestrates the repeated execution of tests based on loop_count / loop_step.

Inspired by workflow engines like Celery, Prefect, and asyncio patterns.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Optional, Awaitable

from domain.models.test_config import TestConfig
from domain.state_machine import (
    SlotStateMachine,
    SlotState,
    SlotEvent,
    SlotContext,
)
from controller.controller import MFCController
from utils.logging import get_logger

if TYPE_CHECKING:
    from domain.enums import ProcessState

logger = get_logger(__name__)


@dataclass
class BatchProgress:
    """Batch execution progress.

    Attributes:
        slot_idx: Slot index.
        current_batch: Current batch number (1-based).
        total_batch: Total batch count.
        current_loop: Current overall loop count.
        total_loop: Total loop count.
        loop_step: Loops per batch.
        progress_percent: Overall progress percentage.
        started_at: Batch execution start time.
        estimated_remaining: Estimated remaining time in seconds.
    """

    slot_idx: int
    current_batch: int
    total_batch: int
    current_loop: int
    total_loop: int
    loop_step: int
    progress_percent: float
    started_at: Optional[datetime] = None
    estimated_remaining: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "slot_idx": self.slot_idx,
            "current_batch": self.current_batch,
            "total_batch": self.total_batch,
            "current_loop": self.current_loop,
            "total_loop": self.total_loop,
            "loop_step": self.loop_step,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "estimated_remaining": self.estimated_remaining,
        }


# Callback type for progress updates
ProgressCallback = Callable[[BatchProgress], Awaitable[None]]


class BatchExecutor:
    """Batch test executor.

    Manages the execution of multi-iteration batch tests.
    Each batch iteration:
    1. Configures MFC with loop_step
    2. Clicks Contact button
    3. Clicks Test button
    4. Waits for Pass state
    5. Repeats until all batches complete

    Example:
        ```python
        executor = BatchExecutor(controller, state_machine)
        await executor.execute(
            slot_idx=0,
            config=test_config,
            on_progress=progress_callback,
        )
        ```
    """

    def __init__(
        self,
        controller: MFCController,
        state_machine: SlotStateMachine,
        poll_interval: float = 1.0,
        pass_wait_timeout: float = 3600.0,  # 1 hour max per batch
    ) -> None:
        """Initialize batch executor.

        Args:
            controller: MFC controller.
            state_machine: Slot state machine.
            poll_interval: Status polling interval in seconds.
            pass_wait_timeout: Max wait time for Pass state per batch.
        """
        self._controller = controller
        self._state_machine = state_machine
        self._poll_interval = poll_interval
        self._pass_wait_timeout = pass_wait_timeout

        # Cancellation support
        self._cancel_requested: dict[int, bool] = {}

    def request_cancel(self, slot_idx: int) -> None:
        """Request cancellation of batch execution.

        Args:
            slot_idx: Slot index to cancel.
        """
        self._cancel_requested[slot_idx] = True
        logger.info("Cancel requested", slot_idx=slot_idx)

    def is_cancel_requested(self, slot_idx: int) -> bool:
        """Check if cancellation is requested.

        Args:
            slot_idx: Slot index.

        Returns:
            True if cancellation requested.
        """
        return self._cancel_requested.get(slot_idx, False)

    def clear_cancel(self, slot_idx: int) -> None:
        """Clear cancellation flag.

        Args:
            slot_idx: Slot index.
        """
        self._cancel_requested.pop(slot_idx, None)

    async def execute(
        self,
        slot_idx: int,
        config: TestConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Execute batch test.

        Runs all batch iterations sequentially.

        Args:
            slot_idx: Slot index.
            config: Test configuration.
            on_progress: Optional progress callback.

        Returns:
            True if all batches completed successfully.
        """
        # Calculate batch count
        total_batch = math.ceil(config.loop_count / config.loop_step)
        started_at = datetime.now()

        logger.info(
            "Starting batch execution",
            slot_idx=slot_idx,
            total_loop=config.loop_count,
            loop_step=config.loop_step,
            total_batch=total_batch,
        )

        # 주의: main.py에서 이미 CONFIGURING 상태로 전이된 상태에서 호출됨
        # 따라서 여기서 START_TEST 트리거하지 않음

        # Context만 업데이트 (상태 전이 없이)
        context = self._state_machine.context
        context.total_loop = config.loop_count
        context.loop_step = config.loop_step
        context.current_batch = 0
        context.total_batch = total_batch
        context.current_loop = 0

        self.clear_cancel(slot_idx)

        try:
            for batch_num in range(1, total_batch + 1):
                # Check for cancellation
                if self.is_cancel_requested(slot_idx):
                    logger.info("Batch execution cancelled", slot_idx=slot_idx)
                    self._state_machine.trigger(SlotEvent.STOP)
                    return False

                # Calculate current loop progress
                current_loop = min(batch_num * config.loop_step, config.loop_count)
                progress_percent = (current_loop / config.loop_count) * 100

                # Update context (상태 전이 없이 context만 업데이트)
                context = self._state_machine.context
                context.current_batch = batch_num
                context.current_loop = (batch_num - 1) * config.loop_step

                # Report progress
                progress = BatchProgress(
                    slot_idx=slot_idx,
                    current_batch=batch_num,
                    total_batch=total_batch,
                    current_loop=(batch_num - 1) * config.loop_step,
                    total_loop=config.loop_count,
                    loop_step=config.loop_step,
                    progress_percent=progress_percent,
                    started_at=started_at,
                )
                if on_progress:
                    await on_progress(progress)

                logger.info(
                    f"Executing batch {batch_num}/{total_batch}",
                    slot_idx=slot_idx,
                    current_loop=current_loop,
                    is_first_batch=(batch_num == 1),
                )

                # Execute single batch
                # 첫 번째 배치만 전체 설정, 이후는 Contact → Test만 실행
                success = await self._execute_single_batch(
                    slot_idx=slot_idx,
                    config=config,
                    is_first_batch=(batch_num == 1),
                )

                if not success:
                    # 취소 요청 또는 Stop 상태인 경우
                    if (
                        self.is_cancel_requested(slot_idx)
                        or self._state_machine.state == SlotState.STOPPING
                    ):
                        logger.info(
                            f"Batch {batch_num} cancelled/stopped",
                            slot_idx=slot_idx,
                        )
                        # STOPPING 상태면 STOPPED 이벤트만 트리거
                        # (이미 _handle_stop_test에서 처리했을 수 있음)
                        return False

                    # 실제 실패인 경우
                    logger.error(
                        f"Batch {batch_num} failed",
                        slot_idx=slot_idx,
                    )
                    # 현재 상태가 FAIL 전이 가능한 상태인지 확인
                    if self._state_machine.can_transition(SlotEvent.FAIL):
                        self._state_machine.trigger(
                            SlotEvent.FAIL,
                            error_message=f"Batch {batch_num} failed",
                        )
                    return False

                # Update progress after batch completion
                self._state_machine.trigger(
                    SlotEvent.BATCH_COMPLETE,
                    context_update={
                        "current_loop": current_loop,
                    },
                )

                # Check if more batches remain
                if batch_num < total_batch:
                    # Trigger next batch
                    self._state_machine.trigger(SlotEvent.BATCH_NEXT)
                else:
                    # All batches done
                    self._state_machine.trigger(SlotEvent.ALL_BATCHES_DONE)

                # Final progress update
                final_progress = BatchProgress(
                    slot_idx=slot_idx,
                    current_batch=batch_num,
                    total_batch=total_batch,
                    current_loop=current_loop,
                    total_loop=config.loop_count,
                    loop_step=config.loop_step,
                    progress_percent=(current_loop / config.loop_count) * 100,
                    started_at=started_at,
                )
                if on_progress:
                    await on_progress(final_progress)

            logger.info(
                "All batches completed successfully",
                slot_idx=slot_idx,
                total_batch=total_batch,
            )
            return True

        except Exception as e:
            logger.error(
                "Batch execution error",
                slot_idx=slot_idx,
                error=str(e),
            )
            # 현재 상태가 ERROR 전이 가능한 상태인지 확인
            if self._state_machine.can_transition(SlotEvent.ERROR):
                self._state_machine.trigger(
                    SlotEvent.ERROR,
                    error_message=str(e),
                )
            return False

    async def _execute_single_batch(
        self,
        slot_idx: int,
        config: TestConfig,
        is_first_batch: bool = True,
    ) -> bool:
        """Execute a single batch iteration.

        Flow:
        - First batch: Full Config → Contact → Test → Wait for Pass
        - Subsequent batches: Contact → Test → Wait for Pass (skip config)

        Args:
            slot_idx: Slot index.
            config: Test configuration.
            is_first_batch: True if this is the first batch (needs full config).

        Returns:
            True if batch completed successfully.
        """
        try:
            if is_first_batch:
                # 첫 번째 배치: 전체 설정 후 테스트 시작
                success = await self._controller.start_test(slot_idx, config)
            else:
                # 이후 배치: Contact → Test만 실행 (설정 유지)
                success = await self._controller.continue_batch(slot_idx)

            if not success:
                return False

            # Transition to RUNNING
            self._state_machine.trigger(SlotEvent.RUN)

            # Wait for Pass state
            pass_detected = await self._wait_for_pass(slot_idx)

            return pass_detected

        except Exception as e:
            logger.error(
                "Single batch execution error",
                slot_idx=slot_idx,
                error=str(e),
            )
            return False

    async def _wait_for_pass(self, slot_idx: int) -> bool:
        """Wait for MFC to reach Pass state.

        Polls the MFC UI directly until Pass or timeout.

        Args:
            slot_idx: Slot index.

        Returns:
            True if Pass state detected.
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < self._pass_wait_timeout:
            # Check for cancellation
            if self.is_cancel_requested(slot_idx):
                return False

            # 직접 MFC UI에서 현재 상태 읽기
            process_state = await self._read_process_state_from_ui(slot_idx)

            if process_state is None:
                await asyncio.sleep(self._poll_interval)
                continue

            # Check for Pass state
            from domain.enums import ProcessState
            if process_state == ProcessState.PASS:
                logger.debug("Pass state detected", slot_idx=slot_idx)
                return True

            # Check for Fail state
            if process_state == ProcessState.FAIL:
                logger.warning("Fail state detected", slot_idx=slot_idx)
                return False

            # Check for Stop state (user cancelled)
            if process_state == ProcessState.STOP:
                logger.info("Stop state detected (user cancelled)", slot_idx=slot_idx)
                return False

            await asyncio.sleep(self._poll_interval)

        logger.error(
            "Timeout waiting for Pass state",
            slot_idx=slot_idx,
            timeout=self._pass_wait_timeout,
        )
        return False

    async def _read_process_state_from_ui(
        self, slot_idx: int
    ) -> "ProcessState | None":
        """Read current process state directly from MFC UI.

        Args:
            slot_idx: Slot index.

        Returns:
            Current ProcessState or None if cannot read.
        """
        from domain.enums import ProcessState

        try:
            # WindowManager를 통해 슬롯 윈도우 가져오기
            slot_window = self._controller.window_manager.get_slot_window(slot_idx)
            if not slot_window or not slot_window.is_connected:
                return None

            # 상태 버튼에서 상태 텍스트 읽기 (Button6 = Pass/Idle/Test/Fail/Stop)
            state_btn = slot_window.get_control_by_name("Button6")
            if state_btn:
                status_text = state_btn.window_text()
                return ProcessState.from_text(status_text)

            return None
        except Exception as e:
            logger.debug(
                "Error reading process state from UI",
                slot_idx=slot_idx,
                error=str(e),
            )
            return None


class BatchExecutorManager:
    """Manager for batch executors across multiple slots.

    Provides a high-level interface for batch test management.
    """

    def __init__(
        self,
        controller: MFCController,
        state_machines: dict[int, SlotStateMachine],
    ) -> None:
        """Initialize manager.

        Args:
            controller: MFC controller.
            state_machines: Dictionary of state machines by slot index.
        """
        self._controller = controller
        self._state_machines = state_machines
        self._executors: dict[int, BatchExecutor] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    def _get_or_create_executor(self, slot_idx: int) -> BatchExecutor:
        """Get or create executor for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            BatchExecutor instance.
        """
        if slot_idx not in self._executors:
            state_machine = self._state_machines.get(slot_idx)
            if not state_machine:
                raise ValueError(f"No state machine for slot {slot_idx}")

            self._executors[slot_idx] = BatchExecutor(
                controller=self._controller,
                state_machine=state_machine,
            )
        return self._executors[slot_idx]

    async def start_batch_test(
        self,
        slot_idx: int,
        config: TestConfig,
        on_progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Start batch test on a slot.

        Args:
            slot_idx: Slot index.
            config: Test configuration.
            on_progress: Optional progress callback.

        Returns:
            True if started successfully.
        """
        # Check if already running
        if slot_idx in self._tasks and not self._tasks[slot_idx].done():
            logger.warning("Batch test already running", slot_idx=slot_idx)
            return False

        executor = self._get_or_create_executor(slot_idx)

        # Create and start task
        task = asyncio.create_task(
            executor.execute(slot_idx, config, on_progress)
        )
        self._tasks[slot_idx] = task

        logger.info("Batch test started", slot_idx=slot_idx)
        return True

    async def stop_batch_test(self, slot_idx: int) -> bool:
        """Stop batch test on a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            True if stop requested successfully.
        """
        if slot_idx not in self._executors:
            return False

        executor = self._executors[slot_idx]
        executor.request_cancel(slot_idx)

        # Also stop on MFC
        await self._controller.stop_test(slot_idx)

        logger.info("Batch test stop requested", slot_idx=slot_idx)
        return True

    def is_running(self, slot_idx: int) -> bool:
        """Check if batch test is running on a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            True if running.
        """
        return (
            slot_idx in self._tasks
            and not self._tasks[slot_idx].done()
        )

    async def wait_for_completion(self, slot_idx: int) -> Optional[bool]:
        """Wait for batch test to complete.

        Args:
            slot_idx: Slot index.

        Returns:
            Test result (True/False) or None if not running.
        """
        if slot_idx not in self._tasks:
            return None

        try:
            return await self._tasks[slot_idx]
        except asyncio.CancelledError:
            return False
        except Exception as e:
            logger.error("Wait for completion error", error=str(e))
            return False
