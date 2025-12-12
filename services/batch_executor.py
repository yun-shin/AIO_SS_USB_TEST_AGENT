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

        Simple structure:
        1. if (precondition enabled) → run precondition → wait for pass
        2. do { run batch → wait for pass } while (batch count)

        Args:
            slot_idx: Slot index.
            config: Test configuration.
            on_progress: Optional progress callback.

        Returns:
            True if all batches completed successfully.
        """
        self.clear_cancel(slot_idx)
        started_at = datetime.now()

        # Debug: Check precondition conditions
        logger.info(
            "Checking precondition requirements",
            slot_idx=slot_idx,
            test_preset=config.test_preset.value,
            is_hot_test=config.test_preset.is_hot_test(),
            precondition_enabled=config.precondition.enabled,
            precondition_capacity=config.precondition.capacity.value
            if config.precondition.capacity
            else None,
            needs_precondition=config.needs_precondition(),
        )

        # === Phase 1: Precondition (if enabled) ===
        if config.needs_precondition():
            logger.info(
                "Phase 1: Running precondition",
                slot_idx=slot_idx,
                capacity=config.precondition.capacity.value
                if config.precondition.capacity
                else "NOT SET",
                method="0HR",
            )

            precond_success = await self._run_precondition(slot_idx, config)
            if not precond_success:
                logger.error("Precondition failed", slot_idx=slot_idx)
                if self._state_machine.can_transition(SlotEvent.FAIL):
                    self._state_machine.trigger(
                        SlotEvent.FAIL, error_message="Precondition failed"
                    )
                return False

            logger.info("Precondition completed", slot_idx=slot_idx)

        # === Phase 2: Main Batches ===
        total_batch = math.ceil(config.loop_count / config.loop_step)
        logger.info(
            "Phase 2: Starting main batches",
            slot_idx=slot_idx,
            total_loop=config.loop_count,
            loop_step=config.loop_step,
            total_batch=total_batch,
        )

        # Initialize context
        context = self._state_machine.context
        context.total_loop = config.loop_count
        context.loop_step = config.loop_step
        context.total_batch = total_batch
        context.is_precondition = False

        batch_num = 0
        while batch_num < total_batch:
            batch_num += 1

            # Check for cancellation
            if self.is_cancel_requested(slot_idx):
                logger.info("Batch execution cancelled", slot_idx=slot_idx)
                self._state_machine.trigger(SlotEvent.STOP)
                return False

            # Update context
            context.current_batch = batch_num
            context.current_loop = (batch_num - 1) * config.loop_step
            current_loop = min(batch_num * config.loop_step, config.loop_count)

            # Report progress
            if on_progress:
                progress = BatchProgress(
                    slot_idx=slot_idx,
                    current_batch=batch_num,
                    total_batch=total_batch,
                    current_loop=context.current_loop,
                    total_loop=config.loop_count,
                    loop_step=config.loop_step,
                    progress_percent=(current_loop / config.loop_count) * 100,
                    started_at=started_at,
                )
                await on_progress(progress)

            logger.info(
                f"Executing batch {batch_num}/{total_batch}",
                slot_idx=slot_idx,
                is_first_batch=(batch_num == 1),
            )

            # Run batch (first: full config, subsequent: contact+test only)
            if batch_num == 1:
                success = await self._controller.start_test(slot_idx, config)
            else:
                success = await self._controller.continue_batch(slot_idx)

            if not success:
                logger.error(f"Batch {batch_num} failed to start", slot_idx=slot_idx)
                if self._state_machine.can_transition(SlotEvent.FAIL):
                    self._state_machine.trigger(
                        SlotEvent.FAIL, error_message=f"Batch {batch_num} failed"
                    )
                return False

            # Transition to RUNNING
            if self._state_machine.can_transition(SlotEvent.RUN):
                self._state_machine.trigger(SlotEvent.RUN)

            # Wait for Pass
            pass_detected = await self._wait_for_pass(slot_idx)
            if not pass_detected:
                if self.is_cancel_requested(slot_idx):
                    logger.info(f"Batch {batch_num} cancelled", slot_idx=slot_idx)
                    return False
                logger.error(f"Batch {batch_num} did not pass", slot_idx=slot_idx)
                if self._state_machine.can_transition(SlotEvent.FAIL):
                    self._state_machine.trigger(
                        SlotEvent.FAIL, error_message=f"Batch {batch_num} failed"
                    )
                return False

            # Batch complete
            self._state_machine.trigger(
                SlotEvent.BATCH_COMPLETE, context_update={"current_loop": current_loop}
            )

            if batch_num < total_batch:
                self._state_machine.trigger(SlotEvent.BATCH_NEXT)

        # All batches done
        self._state_machine.trigger(SlotEvent.ALL_BATCHES_DONE)
        logger.info(
            "All batches completed successfully",
            slot_idx=slot_idx,
            total_batch=total_batch,
        )
        return True

    async def _run_precondition(
        self,
        slot_idx: int,
        config: TestConfig,
    ) -> bool:
        """Run precondition test.

        Creates a precondition config and runs a single test.

        Args:
            slot_idx: Slot index.
            config: Original test configuration.

        Returns:
            True if precondition passed.
        """
        if config.precondition.capacity is None:
            logger.error(
                "Precondition capacity not provided by Backend", slot_idx=slot_idx
            )
            return False

        # Create precondition config
        from domain.models.test_config import TestConfig as TC, PreconditionConfig
        from domain.enums import TestMethod

        precond_config = TC(
            slot_idx=slot_idx,
            jira_no=config.jira_no,
            sample_no=config.sample_no,
            drive=config.drive,
            test_preset=config.test_preset,
            test_file=config.test_file,
            method=TestMethod.ZERO_HR,
            capacity=config.precondition.capacity,
            loop_count=1,
            loop_step=1,
            test_name=f"{config.test_name}_precond",
            drive_capacity_gb=config.drive_capacity_gb,
            precondition=PreconditionConfig(enabled=False),
        )

        # Update context
        context = self._state_machine.context
        context.is_precondition = True
        context.total_loop = 1
        context.current_loop = 0

        # Start precondition test
        success = await self._controller.start_test(slot_idx, precond_config)
        if not success:
            return False

        # Transition to RUNNING
        if self._state_machine.can_transition(SlotEvent.RUN):
            self._state_machine.trigger(SlotEvent.RUN)

        # Wait for Pass
        pass_detected = await self._wait_for_pass(slot_idx)
        context.is_precondition = False

        return pass_detected

    async def _wait_for_pass(self, slot_idx: int) -> bool:
        """Wait for MFC to reach Pass state.

        Polls the MFC UI directly until Pass or timeout.
        First waits for Test state (to ensure new test has started),
        then waits for Pass/Fail result.

        Args:
            slot_idx: Slot index.

        Returns:
            True if Pass state detected.
        """
        from domain.enums import ProcessState

        # 최소 테스트 시간 (초) - 이보다 빨리 Pass가 감지되면 무시
        # 가장 작은 용량(1GB)도 최소 10초 이상 걸림
        MIN_TEST_DURATION = 10.0

        start_time = asyncio.get_event_loop().time()
        test_started = False  # Test 상태 진입 여부 추적
        test_started_time: float | None = None  # Test 상태 진입 시간

        # 첫 폴링 전에 잠시 대기 (MFC UI 업데이트 시간 확보)
        await asyncio.sleep(0.5)

        while asyncio.get_event_loop().time() - start_time < self._pass_wait_timeout:
            # Check for cancellation
            if self.is_cancel_requested(slot_idx):
                return False

            # 직접 MFC UI에서 현재 상태 읽기
            process_state = await self._read_process_state_from_ui(slot_idx)

            logger.debug(
                "Polling MFC state",
                slot_idx=slot_idx,
                process_state=process_state.name if process_state else "None",
                test_started=test_started,
            )

            if process_state is None:
                await asyncio.sleep(self._poll_interval)
                continue

            # 테스트가 아직 시작되지 않은 경우: Test 상태를 기다림
            if not test_started:
                if process_state == ProcessState.TEST:
                    test_started = True
                    test_started_time = asyncio.get_event_loop().time()
                    logger.info(
                        "Test state entered, waiting for result", slot_idx=slot_idx
                    )
                elif process_state in (
                    ProcessState.IDLE,
                    ProcessState.FAIL,
                    ProcessState.PASS,
                ):
                    # 이전 상태가 남아있음 - 테스트 시작 대기
                    await asyncio.sleep(self._poll_interval)
                    continue
                else:
                    await asyncio.sleep(self._poll_interval)
                    continue

            # 테스트가 시작된 후: Pass/Fail 결과 확인
            # Check for Pass state
            if process_state == ProcessState.PASS:
                # 테스트 시작 후 최소 시간이 지나지 않으면 무시 (잘못된 상태 읽기 방지)
                elapsed = asyncio.get_event_loop().time() - (
                    test_started_time or start_time
                )
                if elapsed < MIN_TEST_DURATION:
                    logger.warning(
                        "Pass detected too early, ignoring (likely false positive)",
                        slot_idx=slot_idx,
                        elapsed_seconds=round(elapsed, 1),
                        min_duration=MIN_TEST_DURATION,
                    )
                    await asyncio.sleep(self._poll_interval)
                    continue

                logger.info(
                    "Pass state detected",
                    slot_idx=slot_idx,
                    elapsed_seconds=round(elapsed, 1),
                )
                return True

            # Check for Fail state (only after test started)
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
            test_started=test_started,
        )
        return False

    async def _read_process_state_from_ui(self, slot_idx: int) -> "ProcessState | None":
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
        task = asyncio.create_task(executor.execute(slot_idx, config, on_progress))
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
        return slot_idx in self._tasks and not self._tasks[slot_idx].done()

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
