SS USB Test Agent 설치 안내
=============================

시스템 요구사항
---------------
- Windows 10 이상 (64-bit)
- 최소 100MB 여유 디스크 공간
- USB Test.exe 프로그램 설치 필요

설치 후 설정
------------
1. 설치 완료 후 설정 파일을 수정해야 합니다.
   위치: %APPDATA%\SS USB Test Agent\.env

2. .env 파일에서 다음 항목을 수정하세요:
   - BACKEND_HOST: 백엔드 서버 주소
   - BACKEND_PORT: 백엔드 서버 포트
   - AGENT_ID: 고유 Agent ID (자동 생성)

3. USB Test.exe 프로그램이 설치되어 있어야 합니다.
   기본 경로: C:\Program Files\USB Test\USB Test.exe

문의
----
문제가 발생하면 관리자에게 문의하세요.
