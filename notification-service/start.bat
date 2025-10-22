@echo off
echo ========================================
echo   TrackEneer Notification Service
echo   With IST Timezone Support
echo ========================================
echo.

REM Check if node_modules exists
if not exist "node_modules" (
    echo [1/3] Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo     ^> Dependencies installed successfully!
    echo.
)

REM Check if .env exists
if not exist ".env" (
    echo [2/3] WARNING: .env file not found!
    echo     ^> Copying .env.example to .env...
    copy .env.example .env
    echo.
    echo     ^> Generating VAPID keys...
    call npx web-push generate-vapid-keys
    echo.
    echo     ^> Please update .env with the generated VAPID keys!
    echo     ^> File location: notification-service\.env
    pause
    exit /b 1
)

echo [3/3] Configuration verified!
echo.
echo ^>^>^> Starting notification service on port 3001...
echo ^>^>^> Features: IST Timezone, WebSocket, Push Notifications
echo ^>^>^> Press Ctrl+C to stop
echo.
call npm run dev

pause
