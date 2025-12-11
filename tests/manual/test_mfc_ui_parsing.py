"""MFC UI 파싱 테스트 스크립트.

USB Test.exe 프로그램이 실행 중일 때 각 컨트롤의 값을 읽어옵니다.
수동 테스트용 - USB Test.exe가 실행 중이어야 합니다.

실행 방법:
    python -m tests.manual.test_mfc_ui_parsing
"""

import sys
import time
from typing import Any

# pywinauto 관련
try:
    from pywinauto import Application
    from pywinauto.controls.hwndwrapper import HwndWrapper
except ImportError:
    print("pywinauto가 설치되어 있지 않습니다.")
    print("pip install pywinauto")
    sys.exit(1)


# 테스트할 Control ID들 (AIO_SS_USB_TEST_AGENT 방식)
CONTROL_IDS = {
    "BTN_EXIT": 1000,
    "BTN_CONTACT": 1019,
    "BTN_TEST": 1014,
    "BTN_STOP": 1016,
    "BTN_FORMAT": 1015,
    "CMB_CAPACITY": 1028,
    "CMB_METHOD": 1033,
    "CMB_TEST_TYPE": 1039,
    "CMB_DRIVE": 1029,
    "EDT_LOOP": 1021,
    "EDT_LOOP_CURRENT": 1023,
    "TXT_STATUS": 1034,
    "PROGRESS_BAR": 1035,
    "CHK_IGNORE_FAIL": 1037,  # Ignore Fail checkbox
}

# 기존 AIO_USB_TEST_MACRO에서 사용하는 best match 이름들
BEST_MATCH_NAMES = [
    "Button9",  # 3.0 버전 상태 텍스트
    "Button6",  # 2.0 버전 상태 텍스트
    "Static",   # 테스트 단계 텍스트
    "Edit4",    # 2.0 버전 루프
    "Edit5",    # 3.0 버전 루프
    "ComboBox2",
    "ComboBox3",
    "ComboBox4",
    "MemoryComboBox",
    "ContactButton",
    "TestButton",
    "Ignore FailCheckBox",  # Ignore Fail 체크박스
    "CheckBox2",  # Ignore Fail 체크박스 (alternative name)
]


def find_usb_test_windows() -> list[tuple[Application, Any]]:
    """실행 중인 USB Test 프로세스들을 찾습니다."""
    windows = []

    # 프로세스 이름으로 찾기
    try:
        apps = Application(backend="win32").connect(path="USB Test.exe", timeout=5)
        windows.append(("process", apps))
    except Exception:
        pass

    # 타이틀로 찾기
    try:
        apps = Application(backend="win32").connect(title_re="USB Test.*", timeout=5)
        windows.append(("title", apps))
    except Exception:
        pass

    return windows


def read_control_by_id(dialog: Any, control_id: int, class_name: str | None = None) -> dict:
    """Control ID로 컨트롤을 읽습니다."""
    result = {
        "control_id": control_id,
        "found": False,
        "text": None,
        "enabled": None,
        "visible": None,
        "class_name": None,
        "error": None,
    }

    try:
        # control_id로 찾기
        if class_name:
            ctrl = dialog.child_window(control_id=control_id, class_name=class_name)
        else:
            ctrl = dialog.child_window(control_id=control_id)

        wrapper = ctrl.wrapper_object()
        result["found"] = True
        result["text"] = wrapper.window_text()
        result["enabled"] = wrapper.is_enabled()
        result["visible"] = wrapper.is_visible()
        result["class_name"] = wrapper.friendly_class_name()
    except Exception as e:
        result["error"] = str(e)

    return result


def read_control_by_name(dialog: Any, name: str) -> dict:
    """Best match 이름으로 컨트롤을 읽습니다."""
    result = {
        "name": name,
        "found": False,
        "text": None,
        "enabled": None,
        "visible": None,
        "class_name": None,
        "error": None,
    }

    try:
        # getattr로 접근 (pywinauto best match)
        ctrl = getattr(dialog, name, None)
        if ctrl is None:
            result["error"] = "Control not found via getattr"
            return result

        wrapper = ctrl.wrapper_object() if hasattr(ctrl, "wrapper_object") else ctrl
        result["found"] = True
        result["text"] = wrapper.window_text()
        result["enabled"] = wrapper.is_enabled()
        result["visible"] = wrapper.is_visible()
        result["class_name"] = wrapper.friendly_class_name()
    except Exception as e:
        result["error"] = str(e)

    return result


def print_section(title: str) -> None:
    """섹션 제목을 출력합니다."""
    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)


def main():
    print("MFC UI 파싱 테스트")
    print("-" * 40)
    print("USB Test.exe가 실행 중이어야 합니다.")
    print()

    # USB Test 프로세스 찾기
    print("USB Test 프로세스 검색 중...")

    try:
        app = Application(backend="win32").connect(path="USB Test.exe", timeout=5)
        print(f"✓ USB Test.exe 프로세스 발견")
    except Exception as e:
        print(f"✗ USB Test.exe를 찾을 수 없습니다: {e}")
        print()
        print("USB Test.exe를 먼저 실행해주세요.")
        return

    # 메인 윈도우 가져오기
    try:
        dialog = app.window()
        print(f"✓ 메인 윈도우 연결됨: {dialog.window_text()}")
    except Exception as e:
        print(f"✗ 메인 윈도우를 가져올 수 없습니다: {e}")
        return

    # 1. Control ID 방식으로 읽기 (AIO_SS_USB_TEST_AGENT 방식)
    print_section("Control ID 방식 (AIO_SS_USB_TEST_AGENT)")

    for name, control_id in CONTROL_IDS.items():
        result = read_control_by_id(dialog, control_id)
        if result["found"]:
            print(f"  ✓ {name} (ID={control_id})")
            print(f"      text: '{result['text']}'")
            print(f"      class: {result['class_name']}, enabled: {result['enabled']}")
        else:
            print(f"  ✗ {name} (ID={control_id}): {result['error']}")

    # 2. Best Match 방식으로 읽기 (AIO_USB_TEST_MACRO 방식)
    print_section("Best Match 방식 (AIO_USB_TEST_MACRO)")

    for name in BEST_MATCH_NAMES:
        result = read_control_by_name(dialog, name)
        if result["found"]:
            print(f"  ✓ {name}")
            print(f"      text: '{result['text']}'")
            print(f"      class: {result['class_name']}, enabled: {result['enabled']}")
        else:
            print(f"  ✗ {name}: {result['error']}")

    # 3. 전체 컨트롤 덤프
    print_section("전체 컨트롤 덤프 (print_control_identifiers)")
    print("컨트롤 목록을 출력합니다...")
    print()

    try:
        dialog.print_control_identifiers()
    except Exception as e:
        print(f"컨트롤 목록 출력 실패: {e}")

    # 4. ProcessState 매핑 테스트
    print_section("ProcessState 매핑 테스트")

    # 수정된 from_text 테스트를 위해 import
    from config.constants import ProcessState, TestPhase
    import re

    # TXT_STATUS 읽기
    status_result = read_control_by_id(dialog, 1034)  # TXT_STATUS
    if status_result["found"]:
        raw_text = status_result["text"]
        print(f"  TXT_STATUS (ID=1034) raw text: '{raw_text}'")

        # 진행 텍스트 파싱 테스트
        print()
        print("  진행 텍스트 파싱:")
        match = re.match(r"(\d+)/(\d+)", raw_text.strip())
        if match:
            print(f"    current_loop: {match.group(1)}")
            print(f"    total_loop: {match.group(2)}")
        else:
            print(f"    파싱 실패")

        # TestPhase 파싱
        test_phase = TestPhase.from_text(raw_text)
        print(f"    test_phase: {test_phase.name}")
    else:
        print(f"  ✗ TXT_STATUS를 읽을 수 없습니다: {status_result['error']}")

    # Best Match로도 시도
    print()
    print("  Best Match 방식 상태 읽기:")
    for name in ["Button6", "Button9"]:
        result = read_control_by_name(dialog, name)
        if result["found"]:
            raw_text = result["text"]
            mapped_state = ProcessState.from_text(raw_text)
            print(f"    {name}: '{raw_text}' -> {mapped_state.name}")

    print()
    print("테스트 완료.")


if __name__ == "__main__":
    main()
