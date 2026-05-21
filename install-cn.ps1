$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
$Env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"

function InstallFail {
    Write-Output "安装失败。"
    Read-Host | Out-Null
    Exit
}

function Check {
    param (
        $ErrorInfo
    )
    if (!($?)) {
        Write-Output $ErrorInfo
        InstallFail
    }
}

if (Test-Path -Path "python\python.exe") {
    Write-Output "使用 python 文件夹中的 python..."
    $py_path = (Get-Item "python").FullName
    $env:PATH = "$py_path;$env:PATH"
}
else {
    # Sync vendor/sd-scripts submodule (Anima training engine)
    if ((Test-Path -Path ".git") -or (Test-Path -Path ".git" -PathType Leaf)) {
        Write-Output "同步 git 子模块 (vendor/sd-scripts)..."
        git submodule update --init --recursive
        if ($LASTEXITCODE -ne 0) {
            Write-Output "警告: 子模块初始化失败，Anima 训练可能无法启动。请手动运行: git submodule update --init --recursive"
        }
    }

    if (!(Test-Path -Path "venv")) {
        Write-Output "正在创建虚拟环境..."
        python -m venv venv
        Check "创建虚拟环境失败，请检查 python 是否安装正确以及 python 版本是否为 64 位版本 (python 3.10)，python 的目录是否在环境变量 PATH 中。"
    }

    Write-Output "检测到虚拟环境，正在激活..."
    .\venv\Scripts\activate
    Check "激活虚拟环境失败。"
}

Write-Output "安装训练依赖 (已进行国内加速，如在国外无法使用加速源请换用 install.ps1 脚本)"
Write-Output "注意：在国内加速镜像中 torch 安装无法使用镜像源，安装较为缓慢。"
$install_torch = Read-Host "是否需要安装 Torch+xformers? [y/n] (默认为 y)"
if ($install_torch -eq "y" -or $install_torch -eq "Y" -or $install_torch -eq "") {
    python -m pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --index-url https://download.pytorch.org/whl/cu128
    Check "torch 安装失败，请删除 venv 文件夹后重新运行。"
    python -m pip install -U -I --no-deps xformers===0.0.30 --extra-index-url https://download.pytorch.org/whl/cu128
    Check "xformers 安装失败。"
}

python -m pip install --upgrade -r requirements.txt
Check "训练依赖库安装失败。"


Write-Output "Installing Flash Attention 2 stack (triton-windows + prebuilt wheel)..."
$pyver = python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2>$null
python -m pip install "triton-windows<3.4"
if ($pyver -match "^cp3(10|11|12)$") {
    $whl = "flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-$pyver-$pyver-win_amd64.whl"
    $url = "https://hf-mirror.com/lldacing/flash-attention-windows-wheel/resolve/main/$whl"
    python -m pip install $url 2>$null
} else {
    python -m pip install flash-attn --no-build-isolation 2>$null
}
python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Flash Attention 2 installed and verified"
} else {
    Write-Output "Flash Attention 2 install/self-check failed (non-fatal)"
}

Write-Output "安装完成"
Read-Host | Out-Null
