@echo off
call "%~dp0deploy-local.bat" doctor
set "DEPLOY_RESULT=%errorlevel%"
pause
exit /b %DEPLOY_RESULT%
