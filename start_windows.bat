@echo off
setlocal

cd /d "%~dp0"

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

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"

echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto error

echo Installing project dependencies...
pip install -r requirements.txt
if errorlevel 1 goto error

echo Preparing database...
python manage.py migrate
if errorlevel 1 goto error

echo Loading demo data...
python manage.py seed_demo
if errorlevel 1 goto error

echo.
echo Done. Opening website:
echo http://127.0.0.1:8000/
echo.
echo Operator login: operator
echo Operator password: operator123
echo.
echo Demo customers: customer01 ... customer10
echo Customer password: Mechabear1001
echo.
echo To stop the website, close this window or press Ctrl+C.
echo.

start "" "http://127.0.0.1:8000/"
python manage.py runserver 127.0.0.1:8000
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
