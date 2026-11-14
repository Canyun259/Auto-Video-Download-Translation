@echo off
call "%~dp0deploy-local.bat" update
set "DEPLOY_RESULT=%errorlevel%"
pause
exit /b %DEPLOY_RESULT%
