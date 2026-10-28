@echo off
rem Runs the Spec of Record tool that ships with this plugin from cmd or PowerShell: sor status, sor claim <id>, ...
rem Each candidate is run, not just looked up: the Microsoft Store stub named python3 exists but only prints a message.
set "SOR_TOOLS=%~dp0..\tools\sor.py"
set "CHECK=import sys; sys.exit(sys.version_info < (3, 9))"

call python3 -c "%CHECK%" >nul 2>&1
if not errorlevel 1 goto python3
call python -c "%CHECK%" >nul 2>&1
if not errorlevel 1 goto python
call py -3 -c "%CHECK%" >nul 2>&1
if not errorlevel 1 goto launcher

echo sor: Python 3.9 or newer is needed and none (python3, python or py -3) was found on the PATH 1>&2
exit /b 127

:python3
python3 "%SOR_TOOLS%" %*
exit /b %errorlevel%

:python
python "%SOR_TOOLS%" %*
exit /b %errorlevel%

:launcher
py -3 "%SOR_TOOLS%" %*
exit /b %errorlevel%
