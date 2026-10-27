@echo off
echo ========================================================
echo Starting Project Management System Services (8 Portals Layout)
echo ========================================================
echo.
echo This will launch:
echo 1. Admin Backend   (Port 8000)
echo 2. Panel Backend   (Port 8001)
echo 3. Student Backend (Port 8002)
echo 4. Mentor Backend  (Port 8003)
echo 5. Admin Frontend  (Port 3000)
echo 6. Panel Frontend  (Port 3001)
echo 7. Student Frontend (Port 3002)
echo 8. Mentor Frontend (Port 3003)
echo 9. Main Landing (Port 3004)
echo.

REM Start Backends
start "Admin Backend (8000)" cmd /k "cd /d "%~dp0backend\admin-api" && "%~dp0backend\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
timeout /t 1 /nobreak >nul
start "Panel Backend (8001)" cmd /k "cd /d "%~dp0backend\panel-api" && "%~dp0backend\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001"
timeout /t 1 /nobreak >nul
start "Student Backend (8002)" cmd /k "cd /d "%~dp0backend\student-api" && "%~dp0backend\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002"
timeout /t 1 /nobreak >nul
start "Mentor Backend (8003)" cmd /k "cd /d "%~dp0backend\mentor-api" && "%~dp0backend\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8003"
timeout /t 1 /nobreak >nul

REM Start Frontends
start "Admin Frontend (3000)" cmd /k "cd /d "%~dp0apps\admin" && npm run dev"
timeout /t 1 /nobreak >nul
start "Panel Frontend (3001)" cmd /k "cd /d "%~dp0apps\panel" && npm run dev"
timeout /t 1 /nobreak >nul
start "Student Frontend (3002)" cmd /k "cd /d "%~dp0apps\student" && npm run dev"
timeout /t 1 /nobreak >nul
start "Mentor Frontend (3003)" cmd /k "cd /d "%~dp0apps\mentor" && npm run dev"
timeout /t 1 /nobreak >nul
start "Main Landing (3004)" cmd /k "cd /d "%~dp0apps\main" && npm run dev"

echo.
echo All services have been launched!
echo.
echo URLs:
echo - Admin Portal:   http://localhost:3000 (Backend: 8000)
echo - Panel Portal:   http://localhost:3001 (Backend: 8001)
echo - Student Portal: http://localhost:3002 (Backend: 8002)
echo - Mentor Portal:  http://localhost:3003 (Backend: 8003)
echo - Main Landing:   http://localhost:3004
echo.
pause

