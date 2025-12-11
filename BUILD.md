# 빌드 및 배포 가이드

이 문서는 SS USB Test Agent의 빌드 및 배포 방법을 설명합니다.

---

## 📋 빌드 전략

| 단계 | 도구 | 목적 | 상태 |
|------|------|------|------|
| **1단계** | PyInstaller + Inno Setup | 빠른 개발/테스트 사이클 | ✅ 현재 |
| **2단계** | Nuitka + Inno Setup | 코드 보호 + 성능 최적화 | ⏳ 안정화 후 |

> **참고**: Inno Setup 스크립트는 두 방식 모두에서 재사용됩니다.

---

## 🛠️ 사전 요구사항

### 필수
- Python 3.10+
- pip (최신 버전)

### 빌드 도구 설치
```powershell
# 빌드 의존성 설치
pip install -e ".[build]"

# 또는 직접 설치
pip install pyinstaller>=6.0.0
```

### 설치 프로그램 생성 (선택)
- [Inno Setup 6.x](https://jrsoftware.org/isdl.php) 설치 필요
- 설치 후 `C:\Program Files (x86)\Inno Setup 6\` 확인

---

## 🚀 빌드 방법

### 방법 1: 빌드 스크립트 사용 (권장)

```powershell
# PyInstaller 빌드만
python build/build.py

# PyInstaller + 설치 프로그램
python build/build.py --installer

# 빌드 아티팩트 정리
python build/build.py --clean

# Nuitka 빌드 (향후)
python build/build.py --nuitka
```

### 방법 2: 수동 빌드

```powershell
# 1. PyInstaller로 EXE 생성
pyinstaller build/pyinstaller.spec --clean --noconfirm

# 2. Inno Setup으로 설치 프로그램 생성
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build/installer.iss
```

---

## 📁 빌드 출력

```
dist/
├── SS_USB_Test_Agent/              # PyInstaller 출력
│   ├── SS_USB_Test_Agent.exe       # 실행 파일
│   ├── python310.dll               # Python 런타임
│   ├── *.pyd                       # Python 확장 모듈
│   └── ...
│
└── SS_USB_Test_Agent_Setup_v0.1.0.exe  # Inno Setup 설치 프로그램
```

---

## 📦 배포

### 설치 프로그램 배포

1. `dist/SS_USB_Test_Agent_Setup_v{version}.exe` 파일 배포
2. 사용자는 설치 프로그램 실행 → 설치 완료
3. 설치 후 `.env` 파일 설정 필요

### Portable 배포 (설치 없이)

1. `dist/SS_USB_Test_Agent/` 폴더 전체를 ZIP으로 압축
2. 사용자는 압축 해제 후 `SS_USB_Test_Agent.exe` 직접 실행
3. `.env.example`을 `.env`로 복사하여 설정

---

## ⚙️ 설치 프로그램 기능

Inno Setup으로 생성된 설치 프로그램:

- ✅ 바탕화면 바로가기 (선택)
- ✅ 시작 메뉴 등록
- ✅ Windows 시작 시 자동 실행 (선택)
- ✅ 제어판 프로그램 추가/제거 등록
- ✅ 이전 버전 자동 감지 및 제거
- ✅ 설정 파일 자동 생성 (`%APPDATA%\SS USB Test Agent\.env`)

---

## 🔒 Nuitka 마이그레이션 (향후)

안정화 후 Nuitka로 전환 시:

### 장점
- **코드 보호**: Python 소스 → C 컴파일 (디컴파일 어려움)
- **성능 향상**: 네이티브 코드 실행
- **파일 크기 감소**: 일부 경우에 더 작음

### 전환 방법
```powershell
# Nuitka 설치
pip install nuitka

# C 컴파일러 필요 (둘 중 하나)
# - Visual Studio Build Tools (권장)
# - MinGW-w64

# Nuitka 빌드
python build/build.py --nuitka --installer
```

### 필요 변경사항
1. `build/build.py`의 `build_nuitka()` 함수 검증
2. `requirements.txt`에서 `nuitka` 주석 해제
3. 빌드/테스트 후 배포

---

## 🔧 트러블슈팅

### PyInstaller 빌드 실패

```powershell
# 의존성 재설치
pip install --upgrade pyinstaller

# 캐시 정리 후 재빌드
python build/build.py --clean
python build/build.py
```

### "python310.dll not found" 오류

```powershell
# Python 재설치 또는 PATH 확인
where python
```

### Inno Setup 컴파일러 못 찾음

1. Inno Setup 6.x 설치 확인
2. 설치 경로: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
3. 다른 경로에 설치했다면 `build.py` 수정

### 실행 시 모듈 import 오류

`build/pyinstaller.spec`의 `hiddenimports` 목록에 누락된 모듈 추가:

```python
hiddenimports=[
    "missing_module_name",
    ...
]
```

---

## 📝 버전 업데이트 체크리스트

새 버전 릴리스 시:

1. [ ] `pyproject.toml`의 `version` 수정
2. [ ] `build/version_info.txt`의 버전 정보 수정
3. [ ] `build/installer.iss`의 `MyAppVersion` 수정
4. [ ] `build/build.py`의 `VERSION` 수정
5. [ ] CHANGELOG 업데이트
6. [ ] 빌드 테스트: `python build/build.py --installer`
7. [ ] 설치/제거 테스트
8. [ ] Git 태그 생성: `git tag v0.x.x`
