@echo off
REM OneStats — run the full automated test suite (backend + desktop) on Windows.
REM A .cmd file is NOT blocked by PowerShell's script execution policy, unlike .ps1.
REM Usage:  run-tests.cmd            (both suites)
REM         run-tests.cmd backend    (pytest only)
REM         run-tests.cmd desktop    (vitest only)
setlocal
set ROOT=%~dp0
set WHICH=%1
if "%WHICH%"=="" set WHICH=all

if "%WHICH%"=="all" goto backend
if "%WHICH%"=="backend" goto backend
goto desktop

:backend
echo ============================================================
echo  Backend tests  (pytest; DB tests roll back, no data kept)
echo ============================================================
cd /d "%ROOT%services\api"
call .venv\Scripts\python -m pytest -p no:cacheprovider -q
set BACKEND_RC=%ERRORLEVEL%
if "%WHICH%"=="backend" goto done

:desktop
echo ============================================================
echo  Desktop tests (vitest; logic + jsdom interaction)
echo ============================================================
cd /d "%ROOT%apps\desktop"
call node_modules\.bin\vitest run
set DESKTOP_RC=%ERRORLEVEL%

:done
echo ============================================================
if defined BACKEND_RC echo  backend exit code: %BACKEND_RC%
if defined DESKTOP_RC echo  desktop exit code: %DESKTOP_RC%
echo ============================================================
endlocal
