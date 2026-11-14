@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
 ".venv\Scripts\python.exe" deploy.py %*
 exit /b !errorlevel!
)
py -3.12 -c "import sys; assert sys.maxsize > 2**32" >nul 2>nul
if not errorlevel 1 (
 py -3.12 deploy.py %*
 exit /b !errorlevel!
)
python -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32" >nul 2>nul
if not errorlevel 1 (
 python deploy.py %*
 exit /b !errorlevel!
)
echo Python 3.12 64-bit is required. Install it and reopen this script:
echo winget install --id Python.Python.3.12 --exact
exit /b 1
