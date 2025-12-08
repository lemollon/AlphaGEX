@echo off
echo ========================================
echo Starting AlphaGEX (KRONOS + Backend)
echo ========================================

:: Set the database URL
set DATABASE_URL=postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest

:: Create root .env file if it doesn't exist (backend uses load_dotenv)
if not exist "%~dp0.env" (
    echo Creating .env file...
    echo DATABASE_URL=%DATABASE_URL%> "%~dp0.env"
)

:: Start the backend API in a new window (from backend folder)
echo Starting Backend API...
start "AlphaGEX Backend" cmd /k "cd /d %~dp0backend && set DATABASE_URL=%DATABASE_URL% && python main.py"

:: Wait for backend to fully initialize (needs time to connect to DB)
echo Waiting for backend to initialize...
timeout /t 8 /nobreak > nul

:: Create frontend .env.local if it doesn't exist
if not exist "%~dp0frontend\.env.local" (
    echo Creating frontend .env.local...
    echo NEXT_PUBLIC_API_URL=http://localhost:8000> "%~dp0frontend\.env.local"
    echo NEXT_PUBLIC_WS_URL=ws://localhost:8000>> "%~dp0frontend\.env.local"
)

:: Start the frontend in a new window
echo Starting Frontend (KRONOS)...
start "AlphaGEX Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

:: Wait for frontend to start
timeout /t 5 /nobreak > nul

:: Open browser to KRONOS
echo Opening KRONOS in browser...
start http://localhost:3000/zero-dte-backtest

echo ========================================
echo AlphaGEX is starting!
echo - Backend: http://localhost:8000
echo - Frontend: http://localhost:3000
echo - KRONOS: http://localhost:3000/zero-dte-backtest
echo ========================================
echo You can close this window.
pause
