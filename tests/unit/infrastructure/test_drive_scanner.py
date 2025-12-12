"""Drive scanner tests.

Removable/고정 드라이브 스캔 로직이 필터링과 매핑을 제대로 하는지 검증한다.
"""

import pytest

from infrastructure import drive_scanner


def test_scan_removable_drives_filters_system_and_remote(monkeypatch):
    """[TC-DRIVE-001] 이동식 드라이브 필터링 - 고정/원격 드라이브를 제외한다.

    테스트 목적:
        scan_removable_drives가 고정(FIXED)과 원격(REMOTE)을 제외하고 제거식만 반환하는지 확인한다.

    테스트 시나리오:
        Given: C/D(고정), E(이동식), F(원격) 드라이브 타입을 주입하고
        When: include_fixed=False로 scan_removable_drives를 호출하면
        Then: 반환 목록에 E만 포함되고 label과 is_removable이 기대값이다

    Notes:
        None
    """
    monkeypatch.setattr(
        drive_scanner, "get_logical_drives", lambda: ["C", "D", "E", "F"]
    )
    drive_types = {
        "C": drive_scanner.DRIVE_FIXED,
        "D": drive_scanner.DRIVE_FIXED,
        "E": drive_scanner.DRIVE_REMOVABLE,
        "F": drive_scanner.DRIVE_REMOTE,
    }
    monkeypatch.setattr(drive_scanner, "get_drive_type", lambda letter: drive_types[letter])
    monkeypatch.setattr(
        drive_scanner, "get_volume_info", lambda letter: (f"VOL_{letter}", "NTFS")
    )
    monkeypatch.setattr(
        drive_scanner, "get_drive_space", lambda letter: (1024 * 1024, 512 * 1024)
    )

    drives = drive_scanner.scan_removable_drives(include_fixed=False)

    assert [d.letter for d in drives] == ["E"]
    assert drives[0].label == "VOL_E"
    assert drives[0].is_removable is True


def test_scan_removable_drives_includes_fixed_when_requested(monkeypatch):
    """[TC-DRIVE-002] 고정 포함 옵션 - include_fixed=True이면 고정도 포함한다.

    테스트 목적:
        include_fixed 플래그가 True일 때 고정 드라이브도 결과에 포함되는지 검증한다.

    테스트 시나리오:
        Given: C/D(고정), E(이동식) 드라이브 타입을 주입하고
        When: include_fixed=True로 scan_removable_drives를 호출하면
        Then: 결과에 D와 E가 포함되고 D는 is_removable=False, E는 True다

    Notes:
        None
    """
    monkeypatch.setattr(drive_scanner, "get_logical_drives", lambda: ["C", "D", "E"])
    drive_types = {
        "C": drive_scanner.DRIVE_FIXED,
        "D": drive_scanner.DRIVE_FIXED,
        "E": drive_scanner.DRIVE_REMOVABLE,
    }
    monkeypatch.setattr(drive_scanner, "get_drive_type", lambda letter: drive_types[letter])
    monkeypatch.setattr(
        drive_scanner, "get_volume_info", lambda letter: (f"LABEL_{letter}", "FAT32")
    )
    monkeypatch.setattr(
        drive_scanner, "get_drive_space", lambda letter: (2 * 1024, 1 * 1024)
    )

    drives = drive_scanner.scan_removable_drives(include_fixed=True)

    assert [d.letter for d in drives] == ["D", "E"]
    assert drives[0].is_removable is False
    assert drives[1].is_removable is True


def test_get_drive_info_returns_none_for_unknown(monkeypatch):
    """[TC-DRIVE-003] 알 수 없는 타입 - DRIVE_UNKNOWN이면 None을 반환한다.

    테스트 목적:
        드라이브 타입이 UNKNOWN일 때 get_drive_info가 None을 반환하는지 확인한다.

    테스트 시나리오:
        Given: get_drive_type이 DRIVE_UNKNOWN을 반환하도록 주입하고
        When: get_drive_info("Z")를 호출하면
        Then: 반환값이 None이다

    Notes:
        None
    """
    monkeypatch.setattr(
        drive_scanner, "get_drive_type", lambda letter: drive_scanner.DRIVE_UNKNOWN
    )

    assert drive_scanner.get_drive_info("Z") is None


def test_get_drive_info_builds_driveinfo(monkeypatch):
    """[TC-DRIVE-004] DriveInfo 생성 - 타입/라벨/용량을 조합해 객체를 반환한다.

    테스트 목적:
        get_drive_info가 주입된 타입/라벨/용량 정보를 사용해 DriveInfo를 만드는지 검증한다.

    테스트 시나리오:
        Given: 이동식 타입, 볼륨 라벨, 총/여유 공간 값을 주입하고
        When: get_drive_info("G")를 호출하면
        Then: DriveInfo가 생성되고 letter/label/file_system/size/is_removable이 기대값이다

    Notes:
        None
    """
    monkeypatch.setattr(
        drive_scanner, "get_drive_type", lambda letter: drive_scanner.DRIVE_REMOVABLE
    )
    monkeypatch.setattr(
        drive_scanner, "get_volume_info", lambda letter: ("MYVOL", "NTFS")
    )
    monkeypatch.setattr(
        drive_scanner, "get_drive_space", lambda letter: (10 * 1024, 6 * 1024)
    )

    info = drive_scanner.get_drive_info("G")

    assert info is not None
    assert info.letter == "G"
    assert info.label == "MYVOL"
    assert info.file_system == "NTFS"
    assert info.total_size == 10 * 1024
    assert info.free_size == 6 * 1024
    assert info.is_removable is True
