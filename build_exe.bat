@echo off
:: build_exe.bat
:: -------------
:: Builds KnowledgeMind.exe using PyInstaller.
:: Run this on a Windows machine to produce the distributable .exe
::
:: Prerequisites:
::   pip install pyinstaller
::   pip install -r requirements.txt
::   python -m spacy download en_core_web_sm
::   Node.js 20+ (to build the React front-end)
::
:: Output: dist\KnowledgeMind\KnowledgeMind.exe

echo.
echo [BUILD] Building KnowledgeMind.exe...
echo.

:: Build the React front-end (FastAPI serves frontend\dist) -- REQUIRED
:: The .exe bundles frontend\dist; without it the web UI will not load.
echo [INFO] Building React front-end...
pushd frontend
call npm install
if errorlevel 1 ( echo [ERROR] npm install failed. & popd & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( echo [ERROR] npm run build failed. & popd & pause & exit /b 1 )
popd
echo [OK] Front-end built (frontend\dist)
echo.

:: Clean previous build
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

:: Run PyInstaller
pyinstaller build_windows.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check output above.
    pause
    exit /b 1
)

echo.
echo [OK] Build complete!
echo      Executable: dist\KnowledgeMind\KnowledgeMind.exe
echo      Distribute the entire dist\KnowledgeMind\ folder.
echo.
echo      NOTE: Users still need Ollama installed separately.
echo      Direct them to: https://ollama.com/download
echo.
pause
