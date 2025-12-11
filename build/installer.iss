; Inno Setup Script for SS USB Test Agent
; https://jrsoftware.org/ishelp/
;
; This script creates a professional Windows installer.
; After PyInstaller builds the executable, run this script with Inno Setup Compiler.
;
; Prerequisites:
;   1. Install Inno Setup 6.x from https://jrsoftware.org/isdl.php
;   2. Run PyInstaller first: pyinstaller build/pyinstaller.spec
;   3. Then compile this script: iscc build/installer.iss

#define MyAppName "SS USB Test Agent"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Samsung Electronics"
#define MyAppURL "https://github.com/yun-shin/AIO_SS_USB_TEST_AGENT"
#define MyAppExeName "SS_USB_Test_Agent.exe"
#define MyAppId "{{B8E5F9A2-3D4C-4E6F-8A1B-2C3D4E5F6A7B}"

[Setup]
; 앱 식별 정보
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 설치 경로
DefaultDirName={pf}\AIO\{#MyAppName}
DefaultGroupName=AIO\{#MyAppName}
DisableProgramGroupPage=yes

; 라이선스 및 정보 파일
LicenseFile=assets\LICENSE.txt
InfoBeforeFile=assets\README_INSTALL.txt

; 출력 설정
OutputDir=..\dist
OutputBaseFilename=SS_USB_Test_Agent_Setup_v{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; 압축 설정 (LZMA2 최고 압축)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; 권한 설정
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Windows 버전 요구사항
MinVersion=10.0

; 기타 설정
WizardStyle=modern
WizardSizePercent=100
DisableWelcomePage=no
ShowLanguageDialog=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Windows 시작 시 자동 실행"; GroupDescription: "시작 옵션:"

[Files]
; PyInstaller로 생성된 파일들
Source: "..\dist\SS_USB_Test_Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 설정 파일 (사용자 데이터 폴더에)
Source: "..\dist\SS_USB_Test_Agent\.env.example"; DestDir: "{userappdata}\{#MyAppName}"; DestName: ".env.example"; Flags: ignoreversion

[Dirs]
; 로그 디렉토리 생성
Name: "{userappdata}\{#MyAppName}\logs"; Permissions: users-modify
Name: "{userappdata}\{#MyAppName}\config"; Permissions: users-modify

[Icons]
; 시작 메뉴 바로가기
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; 바탕화면 바로가기 (선택 시)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; 시작 프로그램 (선택 시)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Registry]
; 환경 설정 저장
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "DataPath"; ValueData: "{userappdata}\{#MyAppName}"

[Run]
; 설치 완료 후 실행 옵션
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 제거 시 삭제할 파일/폴더
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\logs"
Type: dirifempty; Name: "{userappdata}\{#MyAppName}"

[Code]
// 설치 전 이전 버전 확인
function InitializeSetup: Boolean;
var
  ResultCode: Integer;
  UninstallString: String;
begin
  Result := True;

  // 이전 버전 확인
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1',
    'UninstallString', UninstallString) then
  begin
    if MsgBox('이전 버전의 {#MyAppName}이 설치되어 있습니다.'#13#10 +
              '계속하면 이전 버전이 제거됩니다.'#13#10#13#10 +
              '계속하시겠습니까?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;

    // 이전 버전 제거
    Exec(RemoveQuotes(UninstallString), '/SILENT', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

// 설치 완료 후 .env 파일 생성 안내
procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvPath := ExpandConstant('{userappdata}\{#MyAppName}');

    // .env 파일이 없으면 .env.example 복사
    if not FileExists(EnvPath + '\.env') then
    begin
      if FileExists(EnvPath + '\.env.example') then
      begin
        FileCopy(EnvPath + '\.env.example', EnvPath + '\.env', False);
      end;
    end;
  end;
end;

// 제거 시 확인
function InitializeUninstall: Boolean;
begin
  Result := True;
  if MsgBox('{#MyAppName}을(를) 제거하시겠습니까?'#13#10 +
            '설정 파일은 유지됩니다.', mbConfirmation, MB_YESNO) = IDNO then
  begin
    Result := False;
  end;
end;
