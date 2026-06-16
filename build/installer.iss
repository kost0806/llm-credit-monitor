#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=LLM Credit Monitor
AppVersion={#AppVersion}
AppPublisher=LLM Credit Monitor
DefaultDirName={autopf}\LLMCreditMonitor
DefaultGroupName=LLM Credit Monitor
OutputDir=..\dist
OutputBaseFilename=LLMCreditMonitor-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=LLM Credit Monitor
PrivilegesRequired=lowest

[Files]
Source: "..\dist\LLMCreditMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LLM Credit Monitor"; Filename: "{app}\LLMCreditMonitor.exe"
Name: "{group}\Uninstall LLM Credit Monitor"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LLMCreditMonitor.exe"; Description: "Launch LLM Credit Monitor"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im LLMCreditMonitor.exe"; Flags: runhidden; RunOnceId: "KillApp"
