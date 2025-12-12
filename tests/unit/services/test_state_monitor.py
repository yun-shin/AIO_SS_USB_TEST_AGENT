"""StateMonitor Unit Tests."""

import asyncio
import pytest
from typing import Any

from services.state_monitor import StateMonitor, SlotSnapshot
from infrastructure.clock import FakeClock
from infrastructure.state_store import FakeStateStore
from infrastructure.window_finder import FakeWindowFinder

from tests.conftest import FakeLogger


class TestStateMonitorBasic:
    """StateMonitor 기본 동작 테스트"""

    @pytest.mark.asyncio
    async def test_start_and_stop(
        self,
        state_monitor: StateMonitor,
    ) -> None:
        """[TC-SMON-001] 시작/종료 - run 플래그가 올바르게 전환된다.

        테스트 목적:
            start와 stop 호출 시 StateMonitor의 is_running 플래그가 적절히 변경되는지 확인한다.

        테스트 시나리오:
            Given: StateMonitor 인스턴스가 있고
            When: start(interval=0.1) 호출 후 stop을 호출하면
            Then: start 후 is_running은 True, stop 후에는 False가 된다

        Notes:
            None
        """
        await state_monitor.start(interval=0.1)
        assert state_monitor.is_running is True

        await state_monitor.stop()
        assert state_monitor.is_running is False

    @pytest.mark.asyncio
    async def test_get_snapshot(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
    ) -> None:
        """[TC-SMON-002] 단일 스냅샷 조회 - 상태/진행도가 반환된다.

        테스트 목적:
            상태 저장소에 기록된 슬롯 상태가 SlotSnapshot으로 올바르게 변환되는지 검증한다.

        테스트 시나리오:
            Given: 슬롯 0에 status/progress/current_phase가 기록돼 있고
            When: get_snapshot(0)을 호출하면
            Then: 반환된 Snapshot에서 슬롯 번호와 필드 값이 저장된 값과 동일하다

        Notes:
            None
        """
        fake_state_store.set_slot_state(
            0,
            {
                "status": "running",
                "progress": 50.0,
                "current_phase": "write",
            },
        )

        snapshot = state_monitor.get_snapshot(0)

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
    ) -> None:
        """[TC-SMON-003] 전체 스냅샷 조회 - 모든 슬롯 상태를 반환한다.

        테스트 목적:
            저장소에 기록된 여러 슬롯의 상태가 리스트로 반환되는지 확인한다.

        테스트 시나리오:
            Given: 슬롯 0/1에 서로 다른 status가 기록돼 있고
            When: get_all_snapshots를 호출하면
            Then: 최소 두 개 이상의 스냅샷이 반환되고 각 슬롯 status가 기록값과 일치한다

        Notes:
            None
        """
        fake_state_store.set_slot_state(0, {"status": "running"})
        fake_state_store.set_slot_state(1, {"status": "idle"})

        snapshots = state_monitor.get_all_snapshots()

        assert len(snapshots) >= 2
        statuses = {s.slot_idx: s.status for s in snapshots}
        assert statuses[0] == "running"
        assert statuses[1] == "idle"


class TestStateMonitorChangeDetection:
    """StateMonitor 상태 변화 감지 테스트"""

    @pytest.mark.asyncio
    async def test_change_callback_invoked(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ) -> None:
        """[TC-SMON-004] 변화 감지 - 상태 변경 시 콜백이 호출된다.

        테스트 목적:
            상태가 바뀔 때 change 콜백이 한 번 호출되고 is_changed 플래그가 True인지 검증한다.

        테스트 시나리오:
            Given: change 콜백을 등록하고 초기 상태를 기록한 뒤
            When: 상태를 idle→running으로 변경하고 _poll_states를 호출하면
            Then: 콜백이 한 번 호출되고 is_changed가 True다

        Notes:
            None
        """
        changes: list[SlotSnapshot] = []

        async def on_change(snapshot: SlotSnapshot) -> None:
            changes.append(snapshot)

        state_monitor.set_change_callback(on_change)

        fake_state_store.set_slot_state(0, {"status": "idle", "progress": 0.0})
        await state_monitor._poll_states()
        assert len(changes) == 1
        assert changes[0].status == "idle"
        changes.clear()

        fake_state_store.set_slot_state(0, {"status": "running", "progress": 10.0})
        await state_monitor._poll_states()

        assert len(changes) == 1
        assert changes[0].slot_idx == 0
        assert changes[0].status == "running"
        assert changes[0].is_changed is True

    @pytest.mark.asyncio
    async def test_no_callback_when_unchanged(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
    ) -> None:
        """[TC-SMON-005] 변화 없음 - 상태가 동일하면 콜백이 호출되지 않는다.

        테스트 목적:
            상태/진행도가 변하지 않은 경우 change 콜백이 호출되지 않는지 확인한다.

        테스트 시나리오:
            Given: change 콜백을 등록하고 상태를 running으로 설정한 뒤
            When: 동일한 상태로 _poll_states를 두 번째 호출하면
            Then: 콜백 호출이 발생하지 않는다

        Notes:
            None
        """
        changes: list[SlotSnapshot] = []

        async def on_change(snapshot: SlotSnapshot) -> None:
            changes.append(snapshot)

        state_monitor.set_change_callback(on_change)

        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})
        await state_monitor._poll_states()
        changes.clear()

        await state_monitor._poll_states()

        assert len(changes) == 0


class TestStateMonitorHangDetection:
    """StateMonitor Hang 감지 테스트"""

    @pytest.mark.asyncio
    async def test_hang_detection_triggered(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ) -> None:
        """[TC-SMON-006] 진행 정지 감지 - 한계 초과 시 hang 콜백을 호출한다.

        테스트 목적:
            running 상태가 정체되어 진행률이 멈추면 hang 콜백이 호출되는지 검증한다.

        테스트 시나리오:
            Given: hang 콜백을 등록하고 running 상태로 기록한 뒤
            When: 시간을 threshold 이상 진전시키고 _poll_states를 호출하면
            Then: hang 콜백이 한 번 호출되고 슬롯/지연 시간이 전달된다

        Notes:
            None
        """
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float) -> None:
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})
        await state_monitor._poll_states()

        fake_clock.advance(seconds=15.0)
        await state_monitor._poll_states()

        assert len(hang_events) == 1
        assert hang_events[0][0] == 0
        assert hang_events[0][1] >= 10.0

    @pytest.mark.asyncio
    async def test_no_hang_when_progress_changes(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ) -> None:
        """[TC-SMON-007] 진행 변화 시 hang 미발생 - 진행률이 변하면 콜백이 없다.

        테스트 목적:
            진행률이 업데이트되면 hang 콜백이 호출되지 않는지 검증한다.

        테스트 시나리오:
            Given: hang 콜백을 등록하고 running 상태로 기록한 뒤
            When: 시간을 경과시키고 progress를 증가시킨 후 _poll_states를 호출하면
            Then: hang 콜백이 호출되지 않는다

        Notes:
            None
        """
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float) -> None:
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        fake_state_store.set_slot_state(0, {"status": "running", "progress": 50.0})
        await state_monitor._poll_states()

        fake_clock.advance(seconds=15.0)
        fake_state_store.set_slot_state(0, {"status": "running", "progress": 60.0})
        await state_monitor._poll_states()

        assert len(hang_events) == 0

    @pytest.mark.asyncio
    async def test_no_hang_when_idle(
        self,
        state_monitor: StateMonitor,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
    ) -> None:
        """[TC-SMON-008] Idle 상태 - 장시간 대기해도 hang 콜백이 없다.

        테스트 목적:
            idle 상태에서는 진행 정지로 간주하지 않아 hang 콜백이 발생하지 않는지 확인한다.

        테스트 시나리오:
            Given: 상태를 idle로 설정하고 hang 콜백을 등록한 뒤
            When: 시간을 크게 경과시키고 _poll_states를 호출하면
            Then: hang 콜백이 호출되지 않는다

        Notes:
            None
        """
        hang_events: list[tuple[int, float]] = []

        async def on_hang(slot_idx: int, duration: float) -> None:
            hang_events.append((slot_idx, duration))

        state_monitor.set_hang_callback(on_hang, threshold_seconds=10.0)

        fake_state_store.set_slot_state(0, {"status": "idle", "progress": 0.0})
        await state_monitor._poll_states()

        fake_clock.advance(seconds=100.0)
        await state_monitor._poll_states()

        assert len(hang_events) == 0
