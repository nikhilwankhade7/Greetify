@echo off
cd /d E:\Project\Greetify\Greetify
taskkill /F /IM python.exe >nul 2>&1
start "Greetify Server" cmd /k "venv\Scripts\activate && python -m uvicorn server:app"
timeout /t 5 >nul
start "" http://127.0.0.1:8000/dashboard
start "Greetify Camera" cmd /k "venv\Scripts\activate && python recognize.py"