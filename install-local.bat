@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-local.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip check
if errorlevel 1 goto failed
echo Installation complete. Double-click start-local.bat.
pause
exit /b 0
:failed
echo Installation failed. Keep this window open and check the error above.
pause
exit /b 1
