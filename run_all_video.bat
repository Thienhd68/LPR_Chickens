@echo off
REM Kích hoạt virtual environment
call .venv\Scripts\activate.bat

REM Chạy main_advanced.py ngầm
start /B python main_advanced.py --source data/Test001.mp4 --save-crops --watchlist watchlist.txt

REM Chạy api_server.py ngầm
start /B python api_server.py

REM Chạy HTTP server ngầm
start /B python -m http.server 8000

REM Chờ vài giây để HTTP server khởi động
timeout /t 3 /nobreak >nul

REM Mở dashboard.html trên trình duyệt
<<<<<<< HEAD
start "" "http://localhost:8000/lpr-dashboard/index.html"
=======
start "" "http://localhost:8000/dashboard.html"
>>>>>>> 17c858e23e5a924344be3a9463c1f3890544ef33

echo All processes started in a single CMD window.
pause
