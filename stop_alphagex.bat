@echo off
echo Stopping AlphaGEX services...

:: Kill Python processes (backend)
taskkill /F /FI "WINDOWTITLE eq AlphaGEX Backend*" >nul 2>&1

:: Kill Node processes (frontend)
taskkill /F /FI "WINDOWTITLE eq AlphaGEX Frontend*" >nul 2>&1

echo AlphaGEX services stopped.
pause
