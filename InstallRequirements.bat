@echo off


echo.
echo ⚙️  Installing packages from requirements.txt...
echo.
cd /d "%~dp0"
if not exist "requirements.txt" (
    echo requirements.txt not found in this folder!
    pause
    exit /b
)
pip install -r requirements.txt
if errorlevel 1 (
    echo Some packages failed to install.
    pause
    exit /b
)
echo.
echo ✅ All packages installed successfully!
pause