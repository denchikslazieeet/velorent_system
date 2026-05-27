@echo off
setlocal

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "VENV_DIR=%PROJECT_DIR%\.venv"

echo.
echo ==========================================
echo  VeloRent: Windows local start
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo Python was not found.
        echo Install Python 3.12 or newer: https://www.python.org/downloads/
        echo During installation enable: Add python.exe to PATH
        echo.
        pause
        exit /b 1
    )
)

if not exist ".env" (
    echo Creating local .env file...
    copy ".env.example" ".env" >nul
)

if exist ".venv\Scripts\activate.bat" (
    findstr /C:"set VIRTUAL_ENV=%VENV_DIR%" ".venv\Scripts\activate.bat" >nul 2>nul
    if errorlevel 1 (
        echo Virtual environment was copied from another folder.
        echo It will be used directly without activation.
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto error
)

set "PYTHON_EXE=.venv\Scripts\python.exe"

echo Checking pip...
"%PYTHON_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo Installing pip into virtual environment...
    "%PYTHON_EXE%" -m ensurepip --upgrade
    if errorlevel 1 goto error
)

echo Updating pip...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto error

echo Installing project dependencies...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo Preparing database...
"%PYTHON_EXE%" manage.py migrate
if errorlevel 1 goto error

echo Loading demo data...
"%PYTHON_EXE%" manage.py seed_demo
if errorlevel 1 goto error

echo.
echo Done. Opening website:
echo http://127.0.0.1:8000/
echo.
echo Operator login: operator
echo Operator password: operator123
echo Operator phone login: 89141301400
echo Operator phone password: Mechabear1001
echo.
echo Demo customers: customer01 ... customer10
echo Customer password: Mechabear1001
echo Customer phone login: 89244702232
echo Customer phone password: Mechabear1001
echo.
echo To stop the website, close this window or press Ctrl+C.
echo.

start "" "http://127.0.0.1:8000/"
"%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000
goto end

:error
echo.
echo Startup failed.
echo Copy the error text from this window and send it to the developer.
echo.
pause
exit /b 1

:end
pause
