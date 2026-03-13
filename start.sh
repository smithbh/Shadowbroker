#!/bin/bash

# Graceful shutdown: kill all child processes on exit/interrupt
trap 'kill 0' EXIT SIGINT SIGTERM

echo "======================================================="
echo "   S H A D O W B R O K E R   -   macOS / Linux Start   "
echo "======================================================="
echo ""

# Check for Node.js
if ! command -v npm &> /dev/null; then
    echo "[!] ERROR: npm is not installed. Please install Node.js 18+ (https://nodejs.org/)"
    exit 1
fi
echo "[*] Found Node.js $(node --version)"

# Check for Python 3
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[!] ERROR: Python is not installed."
    echo "[!] Install Python 3.10-3.12 from https://python.org"
    exit 1
fi

PYVER=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "[*] Found Python $PYVER"
PY_MINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PY_MINOR" -ge 13 ] 2>/dev/null; then
    echo "[!] WARNING: Python $PYVER detected. Some packages may fail to build."
    echo "[!] Recommended: Python 3.10, 3.11, or 3.12."
    echo ""
fi

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "[*] Setting up backend..."
cd "$SCRIPT_DIR/backend"
if [ ! -d "venv" ]; then
    echo "[*] Creating Python virtual environment..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "[!] ERROR: Failed to create virtual environment."
        exit 1
    fi
fi

source venv/bin/activate
echo "[*] Installing Python dependencies (this may take a minute)..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "[!] ERROR: pip install failed. See errors above."
    echo "[!] If you see Rust/cargo errors, your Python version may be too new."
    echo "[!] Recommended: Python 3.10, 3.11, or 3.12."
    exit 1
fi
echo "[*] Backend dependencies OK."
deactivate
echo "[*] Installing backend Node.js dependencies..."
npm install --silent
echo "[*] Backend Node.js dependencies OK."

cd "$SCRIPT_DIR"

echo ""
echo "[*] Setting up frontend..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo "[*] Installing frontend dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "[!] ERROR: npm install failed. See errors above."
        exit 1
    fi
fi
echo "[*] Frontend dependencies OK."

echo ""
echo "======================================================="
echo "  Starting services...                                 "
echo "  Dashboard: http://localhost:3000                     "
echo "  Keep this window open! Initial load takes ~10s.      "
echo "======================================================="
echo "  (Press Ctrl+C to stop)"
echo ""

npm run dev
