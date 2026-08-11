@echo off
echo ============================================
echo    Trackeneer - Starting Application
echo ============================================
echo.

:: Start Backend (Python Flask/FastAPI)
echo [1/2] Starting Backend Server...
start "Trackeneer Backend" cmd /k "cd /d %~dp0server && python app.py"

:: Wait a moment for backend to initialize
timeout /t 3 /nobreak > nul

:: Start Frontend (Next.js)
echo [2/2] Starting Frontend Server...
start "Trackeneer Frontend" cmd /k "cd /d %~dp0client && npm run dev"

echo.
echo ============================================
echo    Both servers are starting!
echo    Backend:  http://localhost:5000
echo    Frontend: http://localhost:3000
echo ============================================
echo.
echo Press any key to open the app in browser...
pause > nul

:: Open browser
start http://localhost:3000
