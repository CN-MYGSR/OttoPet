; 电棍桌宠安装脚本（标准版 / 离线版共用）
; 用法：
;   ISCC.exe /DAppVersion=1.1.5 /DVariant=standard otto_pet.iss
;   ISCC.exe /DAppVersion=1.1.5 /DVariant=offline  otto_pet.iss

#ifndef AppVersion
  #define AppVersion "1.1.5"
#endif
#ifndef Variant
  #define Variant "standard"
#endif

#if Variant == "offline"
  #define AppName "电棍桌宠 离线版"
  #define AppShortName "OttoPet 离线版"
  #define DirSuffix "离线版"
  #define ExeSource "..\dist\otto_pet_offline.exe"
  #define OutputBase "OttoPet-离线版-Setup"
#else
  #define AppName "电棍桌宠 标准版"
  #define AppShortName "OttoPet 标准版"
  #define DirSuffix "标准版"
  #define ExeSource "..\dist\otto_pet.exe"
  #define OutputBase "OttoPet-标准版-Setup"
#endif

[Setup]
#if Variant == "offline"
AppId={{4F3E9B2A-2222-4A7E-9C2D-000000000002}
#else
AppId={{4F3E9B2A-1111-4A7E-9C2D-000000000001}
#endif
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=OttoPet
AppComments=一只在桌面任务栏上溜达的电棍桌宠
DefaultDirName={localappdata}\Programs\OttoPet\{#DirSuffix}
DefaultGroupName=OttoPet
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename={#OutputBase}-{#AppVersion}
SetupIconFile=..\script\otto_icon.ico
UninstallDisplayIcon={app}\otto_pet.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName}
VersionInfoProductName=OttoPet

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#ExeSource}"; DestDir: "{app}"; DestName: "otto_pet.exe"; Flags: ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "使用说明.txt"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppShortName}"; Filename: "{app}\otto_pet.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppShortName}"; Filename: "{app}\otto_pet.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\otto_pet.exe"; Description: "立即启动电棍桌宠"; Flags: nowait postinstall skipifsilent
