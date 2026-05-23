@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title StarvellBot

cd /d "%~dp0"

echo.
echo  ===============================
echo    StarvellBot - launcher
echo  ===============================
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo [x] Python не найден. Установи Python 3.10+ с https://www.python.org/downloads/
    echo     и не забудь галку "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [+] Создаю виртуальное окружение в .venv ...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [x] Не удалось создать venv.
        pause
        exit /b 1
    )

    echo [+] Обновляю pip ...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 (
        echo [!] pip не обновился, продолжаю.
    )

    echo [+] Ставлю зависимости из requirements.txt ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [x] Зависимости не поставились.
        pause
        exit /b 1
    )
) else (
    echo [+] venv уже есть, пропускаю установку.
)

echo.
echo [+] Запускаю StarvellBot ...
echo.

".venv\Scripts\python.exe" app.py
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo [x] Бот завершился с кодом %EXITCODE%.
) else (
    echo [+] Бот остановлен.
)
pause
endlocal
