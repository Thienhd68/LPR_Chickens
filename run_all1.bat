@echo off
chcp 65001 >nul
REM ============================================================
REM LPR System - Khoi dong toan bo he thong
REM Chay ca API Server + Detection Engine + Dashboard
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo [LPR System - Khoi dong he thong]
echo ============================================================
echo.

REM ==================== CHECK PYTHON ====================
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python khong duoc cai dat hoac khong trong PATH
    echo     Vui long cai dat Python tu python.org
    pause
    exit /b 1
)
echo [OK] Python da cai dat

REM ==================== CHECK VENV ====================
if not exist ".venv" (
    echo [!] Virtual environment khong tim thay
    echo [~] Dang tao virtual environment...
    python -m venv .venv
    echo [OK] Virtual environment da tao
)

REM ==================== ACTIVATE VENV ====================
call .venv\Scripts\activate.bat
echo [OK] Virtual environment activated

REM ==================== CHECK DEPENDENCIES ====================
python -c "import torch" >nul 2>&1
if errorlevel 1 (
    echo [!] Dependencies chua cai dat
    echo [~] Dang cai dat requirements...
    pip install -r requirements.txt
    echo [OK] Dependencies cai dat xong
) else (
    echo [OK] Dependencies da san sang
)

REM ==================== START SERVICES ====================
echo.
echo [~] Dang khoi dong cac dich vu...
echo.

REM Khoi dong Flask API Server
echo [*] Khoi dong Flask API Server...
start /B "LPR_API_SERVER" python app.py
if errorlevel 1 (
    echo [X] Loi khoi dong API Server
    pause
    exit /b 1
)
echo [OK] API Server khoi dong

REM Cho API server khoi dong
timeout /t 3 /nobreak >nul

REM ==================== OPEN DASHBOARD ====================
echo.
echo [*] Mo Dashboard...
start "" "http://localhost:5000/"
echo [OK] Dashboard se mo trong trinh duyet

REM ==================== FINAL MESSAGE ====================
echo.
echo ============================================================
echo [OK] Tat ca dich vu da khoi dong!
echo ============================================================
echo.
echo [i] Dashboard:    http://localhost:5000/
echo [i] API Server:   http://localhost:5000/api/
echo.
echo [?] Huong dan:
echo     1. Chon loai camera trong tab "Camera"
echo     2. Click "Bat dau phat hien" de khoi dong
echo     3. Xem ket qua trong cac tab khac
echo.
echo [!] De dung he thong:
echo     - Nhan Ctrl+C trong cua so nay
echo     - Dong cua so Terminal
echo     - Hoac click "Dung detection" trong Dashboard
echo.
echo ============================================================
echo.

REM Gi? cua so mo
pause

REM ==================== CLEANUP ====================
REM Dung tat ca process khi thoat
taskkill /FI "WINDOWTITLE eq LPR_API_SERVER" /F >nul 2>&1

echo.
echo [!] Da thoat LPR System
echo.
pause
