$Env:HF_HOME = "huggingface"

# Ensure the pinned vendor/sd-scripts submodule (Anima training engine) is
# present. Safe to run repeatedly; skips silently when not a git checkout.
if ((Test-Path -Path ".git") -or (Test-Path -Path ".git" -PathType Leaf)) {
    Write-Output "Syncing git submodules (vendor/sd-scripts)..."
    git submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Warning: submodule init failed; Anima training may not start. Run 'git submodule update --init --recursive' manually."
    }
}

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."

pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --extra-index-url https://download.pytorch.org/whl/cu128
pip install -U -I --no-deps xformers==0.0.30 --extra-index-url https://download.pytorch.org/whl/cu128
pip install --upgrade -r requirements.txt

Write-Output "Installing Flash Attention 2 stack (triton-windows + prebuilt wheel)..."
$pyver = python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2>$null
pip install "triton-windows<3.4"
if ($pyver -match "^cp3(10|11|12)$") {
    $whl = "flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-$pyver-$pyver-win_amd64.whl"
    $url = "https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/$whl"
    pip install $url 2>$null
} else {
    pip install flash-attn --no-build-isolation 2>$null
}
python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Flash Attention 2 installed and verified successfully"
} else {
    Write-Output "Flash Attention 2 install/self-check failed (non-fatal, will use xformers or PyTorch SDPA instead)"
}

Write-Output "Install completed"
Read-Host | Out-Null ;
