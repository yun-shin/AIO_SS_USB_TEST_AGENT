"""StateMonitor Unit Tests.

StateMonitor 서비스의 단위 테스트입니다.
"""

import pytest
import asyncio
from typing import Any

from src.services.state_monitor import StateMonitor, SlotSnapshot
from src.infrastructure.clock import FakeClock
from src.infrastructure.state_store import FakeStateStore
from src.infrastructure.window_finder import FakeWindowFinder

from tests.conftest import FakeLogger


class TestStateMonitorBasic:
    """StateMonitor 기본 동작 테스트."""

    @pytest.mark.asyncio
    async def test_start_and_stop(
        self,
        state_monitor: StateMonitor,
    ):
        """모니터 시작/중지 테스트."""
        # When
        await state_monitor.start(interval=0.1)

        # Then
        assert state_monitor.is_running is True

        # When
        await state_monitor.stop()

        # Then
        assert state_monitor.is_running is False

    @pytest.mark.asyncio
    async def test_get_snapshot(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
    ):
        """스냅샷 조회 테스트."""
        # Given
        fake_state_store.set_slot_state(0, {
            "status": "running",
            "progress": 50.0,
            "current_phase": "write",
        })

        # When
        snapshot = state_monitor.get_snapshot(0)

        # Then
        assert snapshot is not None
        assert snapshot.slot_idx == 0
        assert snapshot.status == "running"
        assert snapshot.progress == 50.0
        assert snapshot.current_phase == "write"

    @pytest.mark.asyncio
    async def test_get_all_snapshots(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
    ):
        """모든 스냅샷 조회 테스트."""
        # Given
        fake_state_store.set_slot_state(0, {"status": "running"})
        fake_state_store.set_slot_state(1, {"status": "idle"})

        # When
        snapshots = state_monitor.get_all_snapshots()

        # Then
        assert len(snapshots) >= 2
        statuses = {s.slot_idx: s.status for s in snapshots}
        assert statuses[0] == "running"
        assert statuses[1] == "idle"


class TestStateMonitorChangeDetection:
    """StateMonitor 상태 변경 감지 테스트."""

    @pytest.mark.asyncio
    async def test_change_callback_invoked(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ):
        """상태 변경 시 콜백 호출 테스트."""
        # Given
        changes: list[SlotSnapshot] = []

        async def on_change(snapshot: SlotSnapshot):
            changes.append(snapshot)

        state_monitor.set_change_callback(on_change)

        # 초기 상태 설정 및 폴링 한번 실행 (이전 상태 기록)
        fake_state_store.set_slot_state(0, {"status": "idle", "progress": 0.0})
        await state_monitor._poll_states()

        # When: 상태 변경
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 10.0})
        await state_monitor._poll_states()

        # Then
        assert len(changes) == 1
        assert changes[0].slot_idx == 0
        assert changes[0].status == "running"
        assert changes[0].is_changed is True

    @pytest.mark.asyncio
    async def test_no_callback_when_unchanged(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
    ):
        """상태가 변경되지 않으면 콜백 미호출."""
        # Given
        changes: list[SlotSnapshot] = []

        async def on_change(snapshot: SlotSnapshot):
            changes.append(snapshot)

        state_monitor.set_change_callback(on_change)

        # 상태 설정
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})

        # 첫 번째 폴링 (이전 상태 기록)
        await state_monitor._poll_states()
        changes.clear()

        # When: 동일 상태로 다시 폴링
        await state_monitor._poll_states()

        # Then: 콜백 미호출
        assert len(changes) == 0


class TestStateMonitorHangDetection:
    """StateMonitor Hang 감지 테스트."""

    @pytest.mark.asyncio
    async def test_hang_detection_triggered(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ):
        """Hang 감지 콜백 호출 테스트."""
        # Given
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float):
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        # 초기 상태: running
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})
        await state_monitor._poll_states()

        # When: 시간 경과 (threshold 초과)
        fake_clock.advance(seconds=15.0)
        await state_monitor._poll_states()

        # Then: Hang 감지
        assert len(hang_events) == 1
        assert hang_events[0][0] == 0  # slot_idx
        assert hang_events[0][1] >= 10.0  # duration

    @pytest.mark.asyncio
    async def test_no_hang_when_progress_changes(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ):
        """진행률 변경 시 Hang 미감지."""
        # Given
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float):
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        # 초기 상태
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})
        await state_monitor._poll_states()

        # When: 시간 경과하지만 진행률 변경
        fake_clock.advance(seconds=15.0)
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 60.0})
        await state_monitor._poll_states()

        # Then: Hang 미감지 (진행률이 변경되어 타이머 리셋)
        assert len(hang_events) == 0

    @pytest.mark.asyncio
    async def test_no_hang_when_idle(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ):
        """idle 상태에서는 Hang 미감지."""
        # Given
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float):
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        # idle 상태
        fake_state_store.set_slot_state(0, {"status": "idle", "progress": 0.0})
        await state_monitor._poll_states()

        # When: 오래 대기
        fake_clock.advance(seconds=100.0)
        await state_monitor._poll_states()

        # Then: Hang 미감지
        assert len(hang_events) == 0
