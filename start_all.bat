@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    echo Please install Python 3 and restart this launcher.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js or npm was not found in PATH.
    echo Please install Node.js and restart this launcher.
    pause
    exit /b 1
)

REM --- Backend setup ---
set "BACKEND_DIR=%~dp0app\backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"
set "BACKEND_DEPS_FILE=%BACKEND_DIR%\.deps_ok"
set "BACKEND_NEEDS_INSTALL=0"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating Python virtual environment for backend...
    python -m venv "%VENV_DIR%"
    set "BACKEND_NEEDS_INSTALL=1"
)

if not exist "%BACKEND_DEPS_FILE%" (
    set "BACKEND_NEEDS_INSTALL=1"
)

if exist "%BACKEND_DIR%\requirements.txt" if exist "%BACKEND_DEPS_FILE%" (
    powershell -NoProfile -Command "$req = Get-Item '%BACKEND_DIR%\requirements.txt'; $ok = Get-Item '%BACKEND_DEPS_FILE%'; if ($req.LastWriteTimeUtc -gt $ok.LastWriteTimeUtc) { exit 1 } else { exit 0 }" >nul 2>nul
    if errorlevel 1 set "BACKEND_NEEDS_INSTALL=1"
)

if "%BACKEND_NEEDS_INSTALL%"=="1" (
    echo Installing backend dependencies only if required...
    call "%VENV_DIR%\Scripts\activate.bat"
    cd /d "%BACKEND_DIR%"
    python -m pip install --disable-pip-version-check -r requirements.txt
    type nul > "%BACKEND_DEPS_FILE%"
) else (
    echo Backend dependencies are already up to date.
)

REM --- Speech model for the meeting features (downloaded once, not in git; the app also runs without it) ---
"%VENV_DIR%\Scripts\python.exe" "%~dp0tools\setup\download_asr_model.py"
if errorlevel 1 echo Speech model download failed: meeting captions stay off until tools\setup\download_asr_model.py succeeds.

REM --- Frontend setup ---
set "FRONTEND_DIR=%~dp0app\frontend"
set "FRONTEND_DEPS_FILE=%FRONTEND_DIR%\.deps_ok"
set "FRONTEND_NEEDS_INSTALL=0"

if not exist "%FRONTEND_DIR%\node_modules" (
    set "FRONTEND_NEEDS_INSTALL=1"
)

if not exist "%FRONTEND_DEPS_FILE%" (
    set "FRONTEND_NEEDS_INSTALL=1"
)

if exist "%FRONTEND_DIR%\package.json" if exist "%FRONTEND_DEPS_FILE%" (
    powershell -NoProfile -Command "$pkg = Get-Item '%FRONTEND_DIR%\package.json'; $ok = Get-Item '%FRONTEND_DEPS_FILE%'; if ($pkg.LastWriteTimeUtc -gt $ok.LastWriteTimeUtc) { exit 1 } else { exit 0 }" >nul 2>nul
    if errorlevel 1 set "FRONTEND_NEEDS_INSTALL=1"
)

if "%FRONTEND_NEEDS_INSTALL%"=="1" (
    echo Installing frontend dependencies only if required...
    cd /d "%FRONTEND_DIR%"
    npm install --no-fund --no-audit
    type nul > "%FRONTEND_DEPS_FILE%"
) else (
    echo Frontend dependencies are already up to date.
)

REM --- Launch services ---
if not defined MUDRA_PORT set "MUDRA_PORT=8000"
start "MUDRA Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && ""%VENV_DIR%\Scripts\python.exe"" main.py"

if /i "%~1"=="judges" goto JUDGES

cd /d "%FRONTEND_DIR%"
start "MUDRA Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev -- --host"

echo.
echo MUDRA project started.
echo Backend: http://localhost:%MUDRA_PORT%
echo Frontend: http://localhost:3000
echo.
pause
exit /b 0

:JUDGES
REM Public preview (start_judges.bat, docs/MOBILE_AND_JUDGES.md): the web app on all interfaces with the API on
REM the same origin, then a Cloudflare Quick Tunnel registered with the permanent Worker URL. Needs cloudflared
REM and tools\phone-camera-prototype\cloudflare\update-token.txt (never committed).
echo Waiting for the backend on port %MUDRA_PORT%...
powershell -NoProfile -Command "$ready = $false; for ($i = 0; $i -lt 180; $i++) { try { $h = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $env:MUDRA_PORT + '/health') -TimeoutSec 2; if ($h.status -eq 'ok' -and $h.model_loaded) { $ready = $true; break } } catch { }; Start-Sleep -Seconds 1 }; if (-not $ready) { exit 1 }"
if errorlevel 1 (
    echo ERROR: the backend did not become ready on port %MUDRA_PORT% within 180 seconds. Check the MUDRA Backend window.
    pause
    exit /b 1
)
REM The production build is served (vite preview): the development server's hundreds of small module requests
REM take minutes through a tunnel, the built app loads in seconds.
cd /d "%FRONTEND_DIR%"
set "VITE_API_URL="
call npm run build
if errorlevel 1 (
    echo ERROR: the web app did not build. See the messages above.
    pause
    exit /b 1
)
start "MUDRA Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && set MUDRA_PORT=%MUDRA_PORT%&& set MUDRA_PUBLIC_TUNNEL=1&& npx vite preview --host 0.0.0.0 --port 3000 --strictPort"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_judges_tunnel.ps1"
if errorlevel 1 (
    echo.
    echo ERROR: the public tunnel stopped. Review the messages above before retrying.
    pause
    exit /b 1
)
exit /b 0
