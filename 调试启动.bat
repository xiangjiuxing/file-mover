@echo off
rem Same launcher, but keeps the console open so Python errors stay visible.
set "APP=%~dp0app.py"
where python >nul 2>nul
if %errorlevel%==0 (
    python "%APP%"
    pause
    exit /b 0
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%APP%"
    pause
    exit /b 0
)
echo Python 3.10+ was not found on PATH.
pause
