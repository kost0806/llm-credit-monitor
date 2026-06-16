@echo off
setlocal

cd /d "%~dp0.."

echo [1/3] Installing dependencies...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
)

echo [2/3] Building executable with PyInstaller...
pyinstaller --clean --noconfirm build\llmcreditmonitor.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo [3/3] Building installer with Inno Setup...
where iscc >nul 2>&1
if errorlevel 1 (
    echo WARNING: Inno Setup (iscc) not found in PATH.
    echo          Download from https://jrsoftware.org/isdl.php and add to PATH.
    echo          Skipping installer generation. Executable is at dist\LLMCreditMonitor.exe
) else (
    iscc build\installer.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup failed.
        exit /b 1
    )
    echo Done. Installer: dist\LLMCreditMonitor-Setup.exe
)

echo Build complete.
endlocal
