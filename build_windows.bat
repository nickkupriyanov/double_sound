@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem Сборка портативной версии Double Sound для Windows 10/11 (x64).
rem Результат: dist\DoubleSound\DoubleSound.exe и dist\DoubleSound-win64.zip

cd /d "%~dp0"

set "PYTHON=py -3.11"
where py >nul 2>nul
if errorlevel 1 (
    set "PYTHON=python"
)

echo [1/5] Проверка Python...
%PYTHON% --version
if errorlevel 1 (
    echo.
    echo Python не найден. Установите Python 3.11 x64 с python.org
    echo и повторите запуск.
    pause
    exit /b 1
)

echo [2/5] Виртуальное окружение...
if not exist ".venv\Scripts\python.exe" (
    if exist ".venv" rmdir /s /q ".venv"
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"

echo [3/5] Установка зависимостей...
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :error

echo [4/5] Проверка fpcalc.exe...
if not exist "app\resources\fpcalc.exe" (
    echo fpcalc.exe не найден, скачиваю Chromaprint...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$ErrorActionPreference='Stop';" ^
        "$url='https://github.com/acoustid/chromaprint/releases/download/v1.6.2/chromaprint-fpcalc-1.6.2-windows-x86_64.zip';" ^
        "Invoke-WebRequest -Uri $url -OutFile 'fpcalc.zip';" ^
        "Expand-Archive -Path 'fpcalc.zip' -DestinationPath 'fpcalc_tmp' -Force;" ^
        "$exe = Get-ChildItem -Path 'fpcalc_tmp' -Recurse -Filter 'fpcalc.exe' | Select-Object -First 1;" ^
        "Copy-Item $exe.FullName 'app\resources\fpcalc.exe';" ^
        "Remove-Item 'fpcalc.zip','fpcalc_tmp' -Recurse -Force"
    if errorlevel 1 (
        echo Не удалось скачать fpcalc.exe. Скачайте вручную:
        echo https://github.com/acoustid/chromaprint/releases
        goto :error
    )
)

echo [5/5] Сборка...
python -m pytest -q
if errorlevel 1 goto :error
python -m PyInstaller --noconfirm --clean double_sound.spec
if errorlevel 1 goto :error

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path 'dist\DoubleSound\*' -DestinationPath 'dist\DoubleSound-win64.zip' -Force"

echo.
echo Готово!
echo   Программа: dist\DoubleSound\DoubleSound.exe
echo   Архив:     dist\DoubleSound-win64.zip
echo.
pause
exit /b 0

:error
echo.
echo Сборка не удалась. Смотрите сообщения выше.
pause
exit /b 1
