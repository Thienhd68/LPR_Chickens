@echo off
REM Kích hoạt virtual environment
call .venv\Scripts\activate.bat

REM Chạy main_advanced.py ngầm
start /B python main_advanced.py --source data/Test001.mp4 --save-crops --watchlist watchlist.txt

REM Chạy app.py ngầm (Server API + Frontend)
start /B python app.py

REM Chờ vài giây để HTTP server khởi động
timeout /t 3 /nobreak >nul

REM Mở dashboard.html trên trình duyệt

start "" "http://localhost:5000/"

echo All processes started in a single CMD window.
pause
