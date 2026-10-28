@echo off
REM ============================================================
REM  Disable OneStats SERVER MODE on this PC: the backend goes
REM  back to listening on this computer only (no other machine
REM  can connect), and the firewall rule is removed.
REM  Double-click, then click YES.
REM ============================================================
setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

set "DST=C:\Program Files\OneStats"
set "CFG=%DST%\onestats.env"

echo Closing OneStats if it is running...
taskkill /F /IM desktop.exe >nul 2>&1
taskkill /F /IM onestats-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

if exist "%CFG%" (
  echo Removing ONESTATS_BIND_HOST from the config...
  findstr /V /B /C:"ONESTATS_BIND_HOST=" "%CFG%" > "%CFG%.tmp"
  move /Y "%CFG%.tmp" "%CFG%" >nul
)

echo Removing the firewall rule...
netsh advfirewall firewall delete rule name="OneStats Server" >nul 2>&1

echo.
echo ============================================================
echo  SERVER MODE DISABLED. OneStats now listens on this PC only.
echo  Relaunch OneStats from the desktop icon.
echo ============================================================
echo.
pause
exit /b
