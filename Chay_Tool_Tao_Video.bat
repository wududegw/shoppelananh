@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title FlowKit Studio
set "FLOW_VIDEO_TRANSPORT=ui"
set "MAX_CONCURRENT_REQUESTS=1"
set "STALE_PROCESSING_TIMEOUT=1800"
python --version >nul 2>&1
if errorlevel 1 (
  echo Can cai Python 3.12 va them vao PATH.
  pause
  exit /b 1
)
if not exist "dashboard\dist\index.html" (
  where npm.cmd >nul 2>&1
  if errorlevel 1 (
    echo Can cai Node.js LTS de build dashboard lan dau.
    pause
    exit /b 1
  )
  pushd dashboard
  call npm.cmd ci --no-audit --no-fund
  if errorlevel 1 goto :build_failed
  call npm.cmd run build
  if errorlevel 1 goto :build_failed
  popd
)
if not exist ".env" copy ".env.example" ".env" >nul
python -c "import fastapi, uvicorn, aiosqlite" >nul 2>&1
if errorlevel 1 (
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Khong cai duoc thu vien Python.
    pause
    exit /b 1
  )
)
echo Dashboard: http://127.0.0.1:8100/
echo Studio: http://127.0.0.1:8100/studio
echo Giu tab du an Google Flow mo trong Chrome.
echo Dong cua so nay de dung backend. Khong mo nhieu ban cung luc.
python -c "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8100/health', timeout=2)" >nul 2>&1
if not errorlevel 1 (
  echo Backend da chay. Dang mo dashboard hien tai.
  start "" http://127.0.0.1:8100/
  exit /b 0
)
start "" http://127.0.0.1:8100/
python -m agent.main
pause
exit /b
:build_failed
popd
echo Build dashboard that bai. Xem loi ben tren.
pause
exit /b 1
