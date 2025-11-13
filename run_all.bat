@echo off
REM Kích hoạt virtual environment
call .venv\Scripts\activate.bat

REM Chạy main_advanced.py ngầm (Script nhận diện)
start /B python main_advanced.py --source 0 --save-crops --watchlist watchlist.txt

REM Chạy app.py ngầm (Server API + Frontend)
start /B python app.py

REM Chờ vài giây để server khởi động
timeout /t 3 /nobreak >nul

REM Mở dashboard trên trình duyệt (trỏ vào app.py, không phải http.server)
start "" "http://localhost:5000/"

echo All processes started in a single CMD window.
pause