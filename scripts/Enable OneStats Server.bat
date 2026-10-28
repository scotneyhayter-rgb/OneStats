@echo off
REM ============================================================
REM  Enable OneStats SERVER MODE on this PC, so your other
REM  computers (laptop, researcher) can connect to it over your
REM  Tailscale VPN. Double-click, then click YES.
REM
REM  What it does:
REM   1. Tells the OneStats backend to listen on the network
REM      (ONESTATS_BIND_HOST=0.0.0.0) instead of this PC only.
REM   2. Adds a firewall rule that allows port 8000 ONLY from
REM      Tailscale peers (100.64.0.0/10) - not the public internet.
REM   3. Restarts OneStats and shows the address to give clients.
REM ============================================================
setlocal

REM --- self-elevate (needs admin to edit the install config + firewall) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

set "DST=C:\Program Files\OneStats"
set "CFG=%DST%\onestats.env"
set "PORT=8000"

if not exist "%CFG%" (
  echo ERROR: OneStats config not found at "%CFG%".
  echo Run "Fix OneStats.bat" first to install/configure OneStats, then run this again.
  echo.
  pause
  exit /b
)

echo.
echo Closing OneStats if it is running...
taskkill /F /IM desktop.exe >nul 2>&1
taskkill /F /IM onestats-server.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Enabling server mode (listen on the network)...
findstr /B /C:"ONESTATS_BIND_HOST=" "%CFG%" >nul 2>&1
if errorlevel 1 (
  echo ONESTATS_BIND_HOST=0.0.0.0>>"%CFG%"
  echo   added ONESTATS_BIND_HOST=0.0.0.0 to the config.
) else (
  echo   ONESTATS_BIND_HOST is already set in the config - leaving it as is.
)

echo Adding the firewall rule (Tailscale peers only)...
netsh advfirewall firewall delete rule name="OneStats Server" >nul 2>&1
netsh advfirewall firewall add rule name="OneStats Server" dir=in action=allow protocol=TCP localport=%PORT% remoteip=100.64.0.0/10 >nul
if errorlevel 1 (
  echo WARNING: could not add the firewall rule. You may need to add it manually.
)

echo.
echo ============================================================
echo  SERVER MODE ENABLED.
echo.
echo  On the laptop / researcher PC (after installing OneStats and
echo  joining the same Tailscale network):
echo    Settings -^> Server Connection -^> "Connect to a server"
echo    and enter:   http://THIS-PC-TAILSCALE-IP:%PORT%
echo.
echo  This PC's Tailscale address (100.x.x.x), if Tailscale is running:
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -like '100.*' } ^| Select-Object -First 1 -ExpandProperty IPAddress)" 2^>nul') do echo      http://%%i:%PORT%
echo.
echo  (If nothing shows above, install/sign in to Tailscale, then
echo   run "tailscale ip -4" to find this PC's 100.x.x.x address.)
echo ============================================================
echo.
echo  Now relaunch OneStats from the desktop icon. Keep this PC on
echo  and OneStats running whenever the others need to connect.
echo.
echo  To turn this off later, run "Disable OneStats Server.bat".
echo.
pause
exit /b
