@echo off
setlocal
cd /d "%~dp0"

set "GAME_ROOT=F:\SteamLibrary\steamapps\common\Ratchet & Clank - Rift Apart"
if not exist "%GAME_ROOT%\toc" (
    echo Rift Apart TOC not found at:
    echo   %GAME_ROOT%
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo RCRA Forge environment is missing. Run run.bat once to install it.
    pause
    exit /b 1
)

start "RCRA Forge" /D "%~dp0" ".venv\Scripts\pythonw.exe" "main.py" "%GAME_ROOT%"
