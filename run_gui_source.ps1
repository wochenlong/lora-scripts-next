# Source/venv launcher. Portable packages use run_gui_portable.bat instead.
# Prefer run_gui.bat on Windows (avoids execution policy issues).

$Env:HF_HOME = "huggingface"
$Env:PYTHONUTF8 = "1"
$Env:MIKAZUKI_PORT = "28000"

if (Test-Path -Path "venv\Scripts\activate") {
    Write-Host -ForegroundColor green "Activating virtual environment..."
    .\venv\Scripts\activate
}
elseif (Test-Path -Path "python\python.exe") {
    Write-Host -ForegroundColor green "Using python from python folder..."
    $py_path = (Get-Item "python").FullName
    $env:PATH = "$py_path;$env:PATH"
}
else {
    Write-Host -ForegroundColor Blue "No virtual environment found, using system python..."
}

# Auto-install flash-attn when the pinned triton stack is missing or broken.
python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -c "import triton" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host -ForegroundColor Cyan "Installing triton-windows..."
        pip install "triton-windows<3.4"
    }
    python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host -ForegroundColor Cyan "Installing Flash Attention 2 (prebuilt wheel)..."
        $pyver = python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2>$null
        if ($pyver -match "^cp3(10|11|12)$") {
            $whl = "flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-$pyver-$pyver-win_amd64.whl"
            $url = "https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/$whl"
            pip install $url 2>$null
        } else {
            pip install flash-attn --no-build-isolation 2>$null
        }
        python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host -ForegroundColor Green "Flash Attention 2 installed and verified successfully"
        } else {
            Write-Host -ForegroundColor Yellow "Flash Attention 2 install/self-check failed (non-fatal, using xformers or PyTorch SDPA)"
        }
    }
}

python gui.py @args
