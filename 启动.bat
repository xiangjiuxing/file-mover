@echo off
rem Launch the GUI without a console window.
rem Python is resolved from PATH on purpose: no machine-specific absolute paths.
set "APP=%~dp0app.py"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%APP%"
    exit /b 0
)
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw "%APP%"
    exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%APP%"
    exit /b 0
)
echo Python 3.10+ was not found on PATH. Install Python, or use the packaged EXE.
pause
