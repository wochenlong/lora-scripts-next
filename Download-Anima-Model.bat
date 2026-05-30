@echo off
chcp 65001 >nul 2>&1
title Download Anima Model
cd /d "%~dp0"

set "SCRIPT_DIR=%~dp0"
set "TRAINER_DIR="

if exist "%SCRIPT_DIR%gui.py" (
    set "TRAINER_DIR=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%SD-Trainer\gui.py" (
    set "TRAINER_DIR=%SCRIPT_DIR%SD-Trainer\"
) else (
    echo [Error] SD-Trainer directory not found.
    echo.
    echo Put this bat file in one of these locations:
    echo   1. The portable package root, next to run_gui.bat
    echo   2. The SD-Trainer folder, next to gui.py
    echo.
    pause
    exit /b 1
)

set "MODEL_DIR=%TRAINER_DIR%sd-models\anima"
set "BASE_URL=https://www.modelscope.cn/models/circlestone-labs/Anima/resolve/master/split_files"

echo ============================================================
echo   Anima Model Downloader
echo ============================================================
echo.
echo   Files:
echo     1. anima-base-v1.0.safetensors   (DiT)
echo     2. qwen_3_06b_base.safetensors   (Text Encoder)
echo     3. qwen_image_vae.safetensors    (VAE)
echo.
echo   Save to:
echo     %MODEL_DIR%
echo.
echo   Source: ModelScope (circlestone-labs/Anima)
echo ============================================================
echo.

if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

if exist "%MODEL_DIR%\anima-base-v1.0.safetensors" (
    echo [Skip] anima-base-v1.0.safetensors already exists
) else (
    echo [1/3] Downloading anima-base-v1.0.safetensors ...
    curl -L -# -o "%MODEL_DIR%\anima-base-v1.0.safetensors" "%BASE_URL%/diffusion_models/anima-base-v1.0.safetensors"
    if errorlevel 1 (
        echo       [Failed] Download failed
        del "%MODEL_DIR%\anima-base-v1.0.safetensors" 2>nul
    ) else (
        echo       [OK] Done
    )
)
echo.

if exist "%MODEL_DIR%\qwen_3_06b_base.safetensors" (
    echo [Skip] qwen_3_06b_base.safetensors already exists
) else (
    echo [2/3] Downloading qwen_3_06b_base.safetensors ...
    curl -L -# -o "%MODEL_DIR%\qwen_3_06b_base.safetensors" "%BASE_URL%/text_encoders/qwen_3_06b_base.safetensors"
    if errorlevel 1 (
        echo       [Failed] Download failed
        del "%MODEL_DIR%\qwen_3_06b_base.safetensors" 2>nul
    ) else (
        echo       [OK] Done
    )
)
echo.

if exist "%MODEL_DIR%\qwen_image_vae.safetensors" (
    echo [Skip] qwen_image_vae.safetensors already exists
) else (
    echo [3/3] Downloading qwen_image_vae.safetensors ...
    curl -L -# -o "%MODEL_DIR%\qwen_image_vae.safetensors" "%BASE_URL%/vae/qwen_image_vae.safetensors"
    if errorlevel 1 (
        echo       [Failed] Download failed
        del "%MODEL_DIR%\qwen_image_vae.safetensors" 2>nul
    ) else (
        echo       [OK] Done
    )
)
echo.

echo ============================================================
echo   Download complete
echo.
echo   Model paths for WebUI:
echo     DiT:           ./sd-models/anima/anima-base-v1.0.safetensors
echo     Text Encoder:  ./sd-models/anima/qwen_3_06b_base.safetensors
echo     VAE:           ./sd-models/anima/qwen_image_vae.safetensors
echo ============================================================
pause
