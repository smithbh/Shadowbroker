@echo off
title ShadowBroker - Global Threat Intercept

echo ===================================================
echo     S H A D O W B R O K E R   --   STARTUP
echo ===================================================
echo.

:: Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Python is not installed or not in PATH.
    echo [!] Install Python 3.10-3.12 from https://python.org
    echo [!] IMPORTANT: Check "Add to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: Check Python version (warn if 3.13+)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [*] Found Python %PYVER%
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%b GEQ 13 (
        echo [!] WARNING: Python %PYVER% detected. Some packages may fail to build.
        echo [!] Recommended: Python 3.10, 3.11, or 3.12.
        echo.
    )
)

:: Check for Node.js
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Node.js/npm is not installed or not in PATH.
    echo [!] Install Node.js 18+ from https://nodejs.org
    echo.
    pause
    exit /b 1
)

for /f "tokens=1 delims= " %%v in ('node --version 2^>^&1') do echo [*] Found Node.js %%v

echo.
echo [*] Setting up backend...
cd backend
if not exist "venv\" (
    echo [*] Creating Python virtual environment...
    uv venv
    if %errorlevel% neq 0 (
        echo [!] ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat
echo [*] Installing Python dependencies (this may take a minute)...
uv sync --frozen
if %errorlevel% neq 0 (
    echo.
    echo [!] ERROR: pip install failed. See errors above.
    echo [!] If you see Rust/cargo errors, your Python version may be too new.
    echo [!] Recommended: Python 3.10, 3.11, or 3.12.
    echo.
    pause
    exit /b 1
)
echo [*] Backend dependencies OK.
echo [*] Installing backend Node.js dependencies...
call npm install --silent
echo [*] Backend Node.js dependencies OK.
cd ..

echo.
echo [*] Setting up frontend...
cd frontend
if not exist "node_modules\" (
    echo [*] Installing frontend dependencies...
    call npm install
    if %errorlevel% neq 0 (
        echo [!] ERROR: npm install failed. See errors above.
        pause
        exit /b 1
    )
)
echo [*] Frontend dependencies OK.

echo.
echo ===================================================
echo   Starting services...
echo   Dashboard: http://localhost:3000
echo   Keep this window open! Initial load takes ~10s.
echo ===================================================
echo   (Press Ctrl+C to stop)
echo.

call npm run dev
