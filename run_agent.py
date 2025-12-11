#!/usr/bin/env python
"""Entry point script for SS USB Test Agent.

This script is the main entry point for PyInstaller.
It imports and runs the Agent from the package.
"""

import sys
import asyncio
from pathlib import Path

# PyInstaller frozen 상태 확인
if getattr(sys, "frozen", False):
    # PyInstaller로 빌드된 경우
    BASE_DIR = Path(sys.executable).parent
else:
    # 일반 Python 실행
    BASE_DIR = Path(__file__).parent

# 환경 변수 파일 경로 설정
import os
env_file = BASE_DIR / ".env"
if env_file.exists():
    os.environ.setdefault("DOTENV_PATH", str(env_file))


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    try:
        # Agent 모듈 임포트
        from main import main as agent_main

        # Windows에서 asyncio 이벤트 루프 정책 설정
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        # Agent 실행
        asyncio.run(agent_main())
        return 0

    except KeyboardInterrupt:
        print("\nAgent stopped by user.")
        return 0

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
