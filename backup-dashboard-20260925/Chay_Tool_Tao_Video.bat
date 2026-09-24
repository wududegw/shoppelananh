@echo off
chcp 65001 >nul
title FlowKit Studio - Phan Doan Hoang Edition

echo =====================================================================
echo           FLOWKIT STUDIO - PHAN DOAN HOANG EDITION
echo             Tao Video AI Tu Dong 1-Click Bang Google Flow
echo =====================================================================
echo.

cd /d "%~dp0"
set "FLOW_VIDEO_TRANSPORT=ui"
set "MAX_CONCURRENT_REQUESTS=1"
set "STALE_PROCESSING_TIMEOUT=1800"

:: Kiem tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python 3.10+
    pause
    exit /b 1
)

:: Tat tien trinh cu dang chiem port 8100 (neu co) de cap nhat code moi
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8100" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Kiem tra file .env
if not exist ".env" (
    echo [THONG BAO] Chua co file cau hinh .env.
    echo Neu ban da co Project ID tu flow.google.com, hay nhap vao day:
    echo (Neu chua co, ban co the nhan Enter de cau hinh truc tiep tren Web)
    set /p FLOW_ID="Nhap FLOW_PROJECT_ID: "
    if not "%FLOW_ID%"=="" (
        echo FLOW_PROJECT_ID=%FLOW_ID%> .env
        echo Da luu cau hinh!
    )
)

echo.
echo [1/2] Dang khoi dong may chu FlowKit Backend (Port 8100)...
start /b python -m agent.main

timeout /t 3 /nobreak >nul

echo [2/2] Dang mo giao dien Web Studio tren trinh duyet...
start http://127.0.0.1:8100/studio?v=%RANDOM%

echo.
echo =====================================================================
echo  MAY CHU DANG CHAY TAI: http://127.0.0.1:8100/studio
echo.
echo  Luu y quan trong:
echo  1. Mo trinh duyet Chrome va dang nhap flow.google.com (luon giu tab nay).
echo  2. Vao web http://127.0.0.1:8100/studio de tao video chi voi 1-Click!
echo =====================================================================
echo.
echo Nhan phim bat ky hoac dong cua so nay de tat may chu.
pause >nul
