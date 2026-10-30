@echo off
REM ============================================================
REM  Update OneStats on THIS PC without a full reinstall.
REM
REM  It swaps in the freshly-built application files:
REM    - desktop.exe              (the app + its built-in screens)
REM    - onestats-server-dist\    (the backend engine)
REM  Your database, settings and config file are NOT touched.
REM
REM  Double-click, then click YES at the Windows permission prompt.
REM ============================================================
setlocal

REM --- self-elevate (writing to Program Files needs administrator) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

set "SRC_EXE=C:\OneProjects\OneStats\apps\desktop\src-tauri\target\release\desktop.exe"
set "SRC_SRV=C:\OneProjects\OneStats\apps\desktop\src-tauri\onestats-server-dist"
set "DST=C:\Program Files\OneStats"

if not exist "%SRC_EXE%" (
  echo ERROR: freshly-built app not found at:
  echo    "%SRC_EXE%"
  echo Build it first, then run this again.
  echo.
  pause
  exit /b
)
if not exist "%SRC_SRV%\onestats-server.exe" (
  echo ERROR: freshly-built backend not found at:
  echo    "%SRC_SRV%"
  echo Build it first, then run this again.
  echo.
  pause
  exit /b
)
if not exist "%DST%\desktop.exe" (
  echo ERROR: OneStats is not installed at "%DST%".
  echo Run the full installer once first.
  echo.
  pause
  exit /b
)

echo.
echo Closing OneStats if it is running...
taskkill /F /IM desktop.exe >nul 2>&1
taskkill /F /IM onestats-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Updating the application (desktop.exe)...
copy /Y "%SRC_EXE%" "%DST%\desktop.exe" >nul
if errorlevel 1 (
  echo ERROR: could not update desktop.exe. Is OneStats still open?
  echo.
  pause
  exit /b
)

echo Updating the backend engine (onestats-server-dist)...
robocopy "%SRC_SRV%" "%DST%\onestats-server-dist" /MIR /NFL /NDL /NJH /NJS /NP >nul
REM robocopy returns 0-7 on success; 8+ is a real failure
if %errorlevel% GEQ 8 (
  echo ERROR: could not update the backend engine.
  echo.
  pause
  exit /b
)

echo.
echo ============================================================
echo  OneStats has been updated. Launching it now...
echo.
echo  Note: this updates the app only - it does NOT change your
echo  server-mode setting. If your laptop connects over Tailscale
echo  and cannot reach this PC after the update, run
echo  "Enable OneStats Server.bat" once to re-enable server mode.
echo ============================================================
start "" "%DST%\desktop.exe"
echo.
echo Done - you can close this window.
timeout /t 4 /nobreak >nul
exit /b
