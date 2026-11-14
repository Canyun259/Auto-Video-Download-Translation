@echo off
call "%~dp0deploy-local.bat" install %*
set "DEPLOY_RESULT=%errorlevel%"
pause
exit /b %DEPLOY_RESULT%
