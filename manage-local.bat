@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
 echo Please run install-local.bat first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -c "import psutil, tkinter" >nul 2>nul
if errorlevel 1 (
 echo Please run install-local.bat first.
 pause
 exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0launcher.py" %1
