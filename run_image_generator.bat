@echo off
echo ===================================================
echo       Starting AI Image Generator...
echo ===================================================

:: Create output directory if needed
if not exist "generated_images" mkdir "generated_images"

:: Create placeholder image if needed
if not exist "placeholder.png" (
    echo Creating placeholder image...
    python create_placeholder.py
)

:: Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not found in your PATH. Please install Python 3.8+ and try again.
    goto error
)

:: Display Python version info
echo Python environment:
python --version
python -c "import sys; print(f'Python path: {sys.executable}')"
echo.

:: Check if dependencies are installed
echo Checking dependencies...
python -c "import replicate, customtkinter, PIL" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing required dependencies...
    pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Failed to install dependencies.
        goto error
    )
)

:: Check for Hugging Face dependencies
echo Checking Hugging Face dependencies...
python -c "import diffusers, torch, transformers, safetensors" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Some Hugging Face dependencies are missing.
    echo This is normal if you're using only Replicate API.
    echo If you want to use Hugging Face models, these will be installed when needed.
    echo.
)

:: Check for config file
if not exist "config.json" (
    echo WARNING: No config.json found. A default one will be created.
)

:: Clean up any previous debug logs
if exist "app_debug.log" (
    echo Archiving previous debug log...
    ren "app_debug.log" "app_debug_old.log" >nul 2>nul
)

:: Check disk space
echo Checking disk space...
for /f "tokens=3" %%a in ('dir /-c 2^>nul ^| findstr "bytes free"') do set FREE_SPACE=%%a
echo Available disk space: %FREE_SPACE% bytes

:: Run the application
echo ===================================================
echo Launching AI Image Generator...
echo ===================================================
echo Debug information is being saved to app_debug.log
echo Starting application...
python app.py > app_debug.log 2>&1
set APP_ERROR=%ERRORLEVEL%
echo Application running with process ID: %APP_ERROR%
echo ===================================================
echo Check app_debug.log for detailed messages

if %APP_ERROR% neq 0 (
    echo ERROR: Application crashed or failed to start.
    echo See app_debug.log for details.
    goto error
)

goto end

:error
echo.
echo ===================================================
echo There was an error running the application.
echo Please check app_debug.log for detailed error information.
echo ===================================================
pause
exit /b 1

:end
echo Application closed normally.
echo ===================================================
:: Comment out the line below if you want the command window to close automatically
pause
exit /b 0
