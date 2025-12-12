# SS USB Test Agent 테스트 가이드 (v0.1.0)

본 문서는 AIO_SS_USB_TEST_AGENT에 적용할 테스트 전략입니다. 상위 리포의 일반 규칙(AAA, Given/When/Then docstring, 테스트 실패 시 구현 수정 원칙 등)을 그대로 따르되, 에이전트 특성(윈도우 MFC 제어, WebSocket 양방향 통신, 다중 슬롯, 메모리 모니터링)에 맞춘 세부 항목을 제시합니다.

## 1. 목표와 범위
- **커버리지 목표**: 단위 테스트 90%+, 핵심 경로(상태머신, WebSocket 핸들러, 슬롯 실행/중지 로직, Memory/Process/MFC UI 모니터) 95%+.
- **우선순위 P0**: 상태 전이, WebSocket 명령 처리, MFC 컨트롤러 슬롯 실행/중지, Memory/Process 모니터 경계 상황, WorkerPool 스케줄링.
- **우선순위 P1**: Batch 실행 경계(루프/배치 계산), Enum 변환 헬퍼, 설정 로딩/유효성 검증.
- **우선순위 P2**: 로깅/노이즈 저감, 예외 메시지 일관성.

## 2. 환경 설정
```powershell
cd E:\workspace\AIO_SS_USB_TEST_AGENT
$env:PYTHONPATH = "."
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> **중요**: `ModuleNotFoundError: config` 오류 방지를 위해 `PYTHONPATH="."` 설정 후 `pytest` 실행.

## 3. 테스트 실행
```powershell
# 전체 테스트
pytest

# 단위 테스트만
pytest tests/unit -v

# 커버리지 리포트 (branch 포함 추천)
pytest --cov=. --cov-branch --cov-report=term-missing
```
테스트 실패 시 테스트 약화 금지 원칙 유지(기대값 변경/skip 금지).

## 4. 카테고리별 지침 및 필수 TC

### 4.1 Core / DI / Utils
- **Container 등록/override**: 등록 누락/중복 시 예외, singleton 캐싱 동작, override 후 clear_all_overrides 동작 (P0).
- **Enum 변환(to_capacity/method/preset/file)**: 유효/무효 문자열, 기본값 반환 확인 (P1).

### 4.2 Domain 상태머신
- **유효 전이**: START_TEST → CONFIGURE → RUN → COMPLETE 경로 (P0).
- **에러 전이**: RUN 상태에서 FAIL/ERROR, STOPPING 중 STOPPED, 잘못된 이벤트 시 InvalidTransitionError (P0).
- **배치 컨텍스트**: current_batch/loop_step/total_batch 계산, progress 퍼센트 계산 경계(0, 1, total) (P0).

### 4.3 Infrastructure (Fake/Real Wrapper 단위)
- **FakeWindowFinder/Handle/Control**: 존재/비존재/disabled 시 click/select/set_text 결과, auto_create_window_on_start 동작 (P1).
- **PywinautoWindowFinder**: 타임아웃 시 None 반환, 예외 무시 경계 (Mock Application으로 빠른 단위 테스트) (P2).

### 4.4 Services
- **WorkerPool** (신규 P0)
  - 우선순위 정렬 확인(IMMEDIATE vs NORMAL).
  - max_queue_size 초과 시 drop_if_full 동작 및 로깅.
  - 슬롯별 직렬 실행: 같은 slot_idx 작업 순서 보장, 다른 슬롯 병렬 허용.
- **StateMonitor**: progress 정체 시 hang 콜백 호출, 이전/현재 비교로 is_changed 판단, interval 슬립 모킹 (P1).
- **MemoryMonitor/MemoryManager**:
  - warning/critical 임계치 진입 시 alert 콜백 호출 여부 (GC 모킹).
  - should_optimize 조건 만족 시 optimize 실행, history 크기 제한 (P1).
- **ProcessMonitor**: 감시 대상 추가/제거, 종료 이벤트 콜백 발생, 이미 중지된 PID 처리 (P1).
- **BatchExecutor**:
  - precondition 실행 조건(needs_precondition) 참/거짓.
  - loop_step 경계(1, loop_count, loop_count+1)에서 total_batch 계산.
  - cancel 요청 시 중단, PASS/FAIL/STOP 분기 (P0).

### 4.5 Interface (WebSocket Client)
- **핸드셰이크 파라미터**: API key 유무에 따른 header/query 포함 여부 (P1).
- **재연결**: 연결 실패 시 _handle_reconnect 딜레이 증가/최대 횟수 초과 처리 (Mock websockets.connect) (P0).
- **핸들러 분배**: 등록된 handler 호출, on_message 콜백 예외 처리 시 로깅 후 계속 수신 (P1).

### 4.6 Main 핸들러/워크플로우
- **_handle_start_test**:
  - 잘못된 slot_idx → error state_update 전송.
  - busy 슬롯 → error state_update 전송.
  - config.validate 실패 → ERROR 전이 + state_update.
  - precondition 포함/미포함 파싱, test 필드 누락 시 예외 처리.
  - Batch 모드: loop_step < loop_count일 때 _run_batch_test가 호출되는지 확인.
- **_handle_stop_test**:
  - invalid slot, STOP 불가 상태 → error state_update.
  - stop 성공 시 STOPPED 전이 + state_update.
  - stop 실패 시 ERROR 전이.
- **_on_mfc_ui_polled**:
  - batch/단일 모드 각각 progress 계산 분기 검증.
  - FAIL/STOP/IDLE/TEST 상태별 status 매핑.
- **_on_mfc_test_completed**:
  - batch PASS는 무시, FAIL/STOP은 즉시 전송, 단일 PASS는 test_completed 전송.
- **에러/인터벤션/프로세스 종료 알림**: WorkerPool Top을 거쳐 전송되는지(큐잉 래퍼) (P0).

## 5. 샘플 테스트 스켈레톤
```python
@pytest.mark.asyncio
async def test_start_test_rejects_busy_slot(mocker, fake_setup):
    """[TC-AGENT-START-001] busy 슬롯은 테스트 시작을 거부한다.

    테스트 목적:
        슬롯 상태가 RUNNING일 때 start_test 요청이 에러로 응답하는지 검증한다.

    테스트 시나리오:
        Given: slot_state_machine이 RUNNING 상태
        When: _handle_start_test 호출
        Then: state_update(status=error) 전송, 상태 전이는 없음
    """
    # Arrange: slot_machine.state = RUNNING, ws_client.send_state_update mock
    # Act: await agent._handle_start_test({...})
    # Assert: ws_client.send_state_update 호출, slot_machine 상태 유지
```

## 6. 누락 테스트 및 발견 사항 체크리스트
- [ ] PYTHONPATH 미설정 시 ModuleNotFoundError 발생 → CI/로컬 공통 환경 변수 설정 필요.
- [ ] WorkerPool 외 서비스(Time/Process/Memory/MFC UI) 경계 테스트 추가 필요.
- [ ] BatchExecutor 취소/실패 경로 테스트 미구현.
- [ ] WebSocket 재연결/heartbeat 타임아웃 경계 미구현.
- [ ] TODO 구간(실제 MFC UI 읽기/로그 수집/Health Report 실행) 구현 후 단위 테스트 필수.

## 7. 실행/CI 권장 옵션
```ini
# pytest.ini 예시
[pytest]
testpaths = tests
python_files = test_*.py
asyncio_mode = auto
addopts = --strict-markers --tb=short
markers =
    unit: Unit tests
    integration: Integration tests
```
CI에서는 `PYTHONPATH="." pytest --cov=. --cov-branch --cov-report=xml` 실행을 권장합니다.
