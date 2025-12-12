#!/usr/bin/env python
"""Build script for SS USB Test Agent.

This script automates the build process:
1. Clean previous builds
2. Run PyInstaller to create executable
3. Run Inno Setup to create installer

Usage:
    python build/build.py              # PyInstaller + Inno Setup (full build)
    python build/build.py --no-installer  # PyInstaller only (no installer)
    python build/build.py --installer-only  # Inno Setup only (skip PyInstaller)
    python build/build.py --clean      # Clean build artifacts
    python build/build.py --nuitka     # Use Nuitka (future)

Requirements:
    - pyinstaller (pip install pyinstaller)
    - Inno Setup 6.x (https://jrsoftware.org/isdl.php)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
SPEC_FILE = BUILD_DIR / "pyinstaller.spec"
ISS_FILE = BUILD_DIR / "installer.iss"

# 앱 정보
APP_NAME = "SS_USB_Test_Agent"
VERSION = "0.1.0"


def run_command(cmd: list[str], cwd: Optional[Path] = None) -> bool:
    """명령어 실행.

    Args:
        cmd: 실행할 명령어 리스트.
        cwd: 작업 디렉토리.

    Returns:
        성공 여부.
    """
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            check=True,
            capture_output=False,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}")
        return False


def clean_build() -> None:
    """빌드 아티팩트 정리."""
    print("\n=== Cleaning build artifacts ===")

    dirs_to_clean = [
        DIST_DIR,
        PROJECT_ROOT / "build" / APP_NAME,
        PROJECT_ROOT / "__pycache__",
    ]

    # .spec 파일이 생성하는 빌드 디렉토리
    spec_build_dir = PROJECT_ROOT / "build" / APP_NAME
    if spec_build_dir.exists():
        dirs_to_clean.append(spec_build_dir)

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            print(f"  Removing: {dir_path}")
            shutil.rmtree(dir_path, ignore_errors=True)

    # .pyc 파일 제거
    for pyc in PROJECT_ROOT.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)

    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)

    print("  Done.")


def build_pyinstaller() -> bool:
    """PyInstaller로 빌드."""
    print("\n=== Building with PyInstaller ===")

    # dist 디렉토리 생성
    DIST_DIR.mkdir(exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE),
    ]

    return run_command(cmd)


def build_nuitka() -> bool:
    """Nuitka로 빌드 (향후 구현).

    Nuitka는 Python 코드를 C로 컴파일하여:
    - 더 나은 성능
    - 코드 보호 (디컴파일 어려움)
    - 더 작은 파일 크기 (일부 경우)
    """
    print("\n=== Building with Nuitka ===")
    print("Note: Nuitka build requires additional setup.")
    print("Install: pip install nuitka")
    print("Also need: C compiler (MSVC or MinGW)")

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",  # 단일 파일 (선택)
        "--windows-console-mode=attach",  # 콘솔 창 표시
        "--enable-plugin=anti-bloat",  # 불필요한 import 제거
        f"--output-dir={DIST_DIR}",
        f"--output-filename={APP_NAME}.exe",
        # Windows 정보
        f"--windows-product-name={APP_NAME}",
        f"--windows-product-version={VERSION}",
        "--windows-company-name=Samsung Electronics",
        # 아이콘 (있으면)
        # f"--windows-icon-from-ico={BUILD_DIR / 'assets' / 'icon.ico'}",
        # 포함할 패키지
        "--include-package=pywinauto",
        "--include-package=pydantic",
        # structlog removed - using standard logging
        # 제외할 패키지
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=mypy",
        "--nofollow-import-to=ruff",
        str(PROJECT_ROOT / "run_agent.py"),
    ]

    return run_command(cmd)


def build_installer() -> bool:
    """Inno Setup으로 설치 프로그램 생성."""
    print("\n=== Building Installer with Inno Setup ===")

    # Inno Setup 컴파일러 경로 찾기
    iscc_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]

    iscc_path = None
    for path in iscc_paths:
        if path.exists():
            iscc_path = path
            break

    if not iscc_path:
        print("Error: Inno Setup not found.")
        print("Please install from: https://jrsoftware.org/isdl.php")
        return False

    # PyInstaller 결과물 확인
    exe_path = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"Error: PyInstaller output not found: {exe_path}")
        print("Run 'python build/build.py' first.")
        return False

    cmd = [str(iscc_path), str(ISS_FILE)]
    return run_command(cmd, cwd=BUILD_DIR)


def main() -> int:
    """메인 함수."""
    parser = argparse.ArgumentParser(description="Build SS USB Test Agent")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument(
        "--no-installer",
        action="store_true",
        help="Skip installer build (PyInstaller only)",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Build installer only (skip PyInstaller)",
    )
    parser.add_argument(
        "--nuitka", action="store_true", help="Use Nuitka instead of PyInstaller"
    )

    args = parser.parse_args()

    print(f"SS USB Test Agent Build Script v{VERSION}")
    print("=" * 50)

    # 정리만 수행
    if args.clean:
        clean_build()
        if not args.installer_only:
            return 0

    # 빌드 (installer-only가 아닌 경우)
    if not args.installer_only:
        clean_build()

        if args.nuitka:
            success = build_nuitka()
        else:
            success = build_pyinstaller()

        if not success:
            print("\n!!! Build failed !!!")
            return 1

        print("\n✓ Build successful!")
        print(f"  Output: {DIST_DIR / APP_NAME}")

    # 설치 프로그램 생성 (no-installer가 아닌 경우)
    if not args.no_installer:
        if not build_installer():
            print("\n!!! Installer build failed !!!")
            return 1

        installer_name = f"{APP_NAME}_Setup_v{VERSION}.exe"
        print(f"\n✓ Installer created!")
        print(f"  Output: {DIST_DIR / installer_name}")

    print("\n" + "=" * 50)
    print("Build completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
