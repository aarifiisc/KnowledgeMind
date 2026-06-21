@echo off
:: launch_windows.bat
:: ------------------
:: Windows launcher for KnowledgeMind (without PyInstaller build).
:: Creates a venv, installs deps, and starts the app.
::
:: Usage: Double-click launch_windows.bat
::        Or run from command prompt: launch_windows.bat

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PYTHON_VENV=%VENV_DIR%\Scripts\python.exe"
set "PIP_VENV=%VENV_DIR%\Scripts\pip.exe"

echo.
echo   KnowledgeMind
echo   Privacy-Aware Personal AI Agent
echo   IISc Bengaluru
echo.

:: ── Check Python ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://www.python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

:: ── Check Ollama ──────────────────────────────────────────────────────────
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama not found. Install from https://ollama.com/download
    echo        You can still configure API keys, but local model needs Ollama.
) else (
    echo [OK] Ollama found
)

:: ── Create venv if needed ─────────────────────────────────────────────────
if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

:: ── Install dependencies ──────────────────────────────────────────────────
echo [INFO] Checking dependencies (may take a few minutes on first run)...
"%PIP_VENV%" install -r "%SCRIPT_DIR%requirements.txt" --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies ready

:: ── spaCy model ───────────────────────────────────────────────────────────
"%PYTHON_VENV%" -c "import en_core_web_sm" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Downloading spaCy English model...
    "%PYTHON_VENV%" -m spacy download en_core_web_sm --quiet
    echo [OK] spaCy model installed
) else (
    echo [OK] spaCy model ready
)

:: ── Create data directory ─────────────────────────────────────────────────
if not exist "%SCRIPT_DIR%data" mkdir "%SCRIPT_DIR%data"

:: ── Launch ────────────────────────────────────────────────────────────────
echo.
echo [INFO] Starting KnowledgeMind at http://127.0.0.1:7860 ...
echo        Your browser will open automatically.
echo        Close this window to stop the app.
echo.

"%PYTHON_VENV%" "%SCRIPT_DIR%launcher.py"

if errorlevel 1 (
    echo.
    echo [ERROR] KnowledgeMind exited with an error. See output above.
    pause
)
