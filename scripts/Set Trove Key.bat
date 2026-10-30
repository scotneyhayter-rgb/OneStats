@echo off
REM ============================================================
REM  Set the Trove API key for OneStats newspaper search.
REM
REM  It writes ONESTATS_TROVE_API_KEY into the OneStats config
REM  (C:\Program Files\OneStats\onestats.env) and restarts the
REM  app so the key takes effect. The key stays on this PC.
REM
REM  Get a free key at trove.nla.gov.au (your account -> Trove API).
REM  Double-click this file, click YES, then paste your key.
REM ============================================================
setlocal

REM --- self-elevate (editing the config in Program Files needs administrator) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

set "CFG=C:\Program Files\OneStats\onestats.env"
set "DST=C:\Program Files\OneStats"

if not exist "%CFG%" (
  echo ERROR: OneStats config not found at:
  echo    "%CFG%"
  echo Install/run OneStats first, then run this again.
  echo.
  pause
  exit /b
)

echo.
echo Paste your Trove API key, then press Enter.
echo (Get one free at trove.nla.gov.au - your account, Trove API tab.)
echo.
set "KEY="
set /p "KEY=Trove API key: "

REM strip surrounding quotes if the user pasted them
set "KEY=%KEY:"=%"

if "%KEY%"=="" (
  echo.
  echo No key entered - nothing changed.
  echo.
  pause
  exit /b
)

echo.
echo Closing OneStats if it is running...
taskkill /F /IM desktop.exe >nul 2>&1
taskkill /F /IM onestats-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Saving the key to the OneStats config...
set "TMP=%CFG%.new"
REM keep every line except any existing Trove key line
findstr /v /b /c:"ONESTATS_TROVE_API_KEY=" "%CFG%" > "%TMP%"
>> "%TMP%" echo ONESTATS_TROVE_API_KEY=%KEY%
move /y "%TMP%" "%CFG%" >nul
if errorlevel 1 (
  echo ERROR: could not update the config.
  echo.
  pause
  exit /b
)

echo.
echo ============================================================
echo  Trove API key saved. Launching OneStats...
echo.
echo  Open the Research Centre -> Newspaper Search and try a
echo  search (e.g. "Moyston cricket", 1890-1910). The "no key"
echo  message should be gone.
echo ============================================================
start "" "%DST%\desktop.exe"
echo.
echo Done - you can close this window.
timeout /t 4 /nobreak >nul
exit /b
