$Env:HF_HOME = "huggingface"
$Env:MIKAZUKI_TAGGER_MODELS_DIR = "tagger-models"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
$Env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"

. "$PSScriptRoot\install_preflight.ps1"

function InstallFail {
    Write-Output "安装失败。"
    Read-Host | Out-Null
    Exit 1
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

$PytorchSources = @(
    @{
        Name = "阿里云 PyTorch Wheels"
        Mode = "find-links"
        Url = "https://mirrors.aliyun.com/pytorch-wheels/cu128/"
    },
    @{
        Name = "SJTUG PyTorch Wheels"
        Mode = "index-url"
        Url = "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128"
    },
    @{
        Name = "PyTorch Official"
        Mode = "index-url"
        Url = "https://download.pytorch.org/whl/cu128"
    }
)

function Test-PytorchSource {
    param ($Source)

    $start = Get-Date
    try {
        Invoke-WebRequest -Uri $Source.Url -UseBasicParsing -TimeoutSec 8 | Out-Null
        $elapsed = ((Get-Date) - $start).TotalSeconds
        [PSCustomObject]@{
            Name = $Source.Name
            Mode = $Source.Mode
            Url = $Source.Url
            Elapsed = $elapsed
            Ok = $true
        }
    }
    catch {
        [PSCustomObject]@{
            Name = $Source.Name
            Mode = $Source.Mode
            Url = $Source.Url
            Elapsed = [double]::PositiveInfinity
            Ok = $false
            Error = $_.Exception.Message
        }
    }
}

function Select-PytorchSources {
    Write-Host "正在测速 PyTorch 下载源..."
    $jobs = foreach ($source in $PytorchSources) {
        Start-Job -ScriptBlock ${function:Test-PytorchSource} -ArgumentList $source
    }

    $results = @()
    while ($jobs.Count -gt 0) {
        $completed = Wait-Job -Job $jobs -Any
        $result = Receive-Job -Job $completed
        Remove-Job -Job $completed
        $jobs = @($jobs | Where-Object { $_.Id -ne $completed.Id })
        $results += $result

        if ($result.Ok) {
            Write-Host ("  OK   {0} ({1:N2}s)" -f $result.Name, $result.Elapsed)
        }
        else {
            Write-Host ("  FAIL {0} ({1})" -f $result.Name, $result.Error)
        }
    }

    $available = @($results | Where-Object { $_.Ok } | Sort-Object Elapsed)
    if ($available.Count -eq 0) {
        Write-Host "所有 PyTorch 下载源均无法连接，请检查网络或代理设置后重试。"
        InstallFail
    }

    Write-Host ("已选择最快源: {0}" -f $available[0].Name)
    return $available
}

function Get-PipSourceArgs {
    param ($Source)

    if ($Source.Mode -eq "find-links") {
        return @("-f", $Source.Url)
    }
    return @("--index-url", $Source.Url)
}

if (-not (Test-InstallScriptFreshness)) { InstallFail }

if (Test-Path -Path "python\python.exe") {
    Write-Output "使用 python 文件夹中的 python..."
    $py_path = (Get-Item "python").FullName
    $env:PATH = "$py_path;$env:PATH"
    if (-not (Test-InstallPython)) { InstallFail }
}
else {
    if (-not (Test-InstallPython)) { InstallFail }

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
Write-Output "Torch 将自动测速多个下载源并选择最快可用源。"
$install_torch = Read-Host "是否需要安装 Torch+xformers? [y/n] (默认为 y)"
if ($install_torch -eq "y" -or $install_torch -eq "Y" -or $install_torch -eq "") {
    $pytorchSources = @(Select-PytorchSources)
    $pytorchSource = $null
    $pytorchSourceArgs = $null
    $torchInstalled = $false

    foreach ($source in $pytorchSources) {
        if ($pytorchSource -ne $null) {
            Write-Output ("正在尝试备用源: {0}" -f $source.Name)
        }
        $pytorchSource = $source
        $pytorchSourceArgs = Get-PipSourceArgs $source
        python -m pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 @pytorchSourceArgs
        if ($LASTEXITCODE -eq 0) {
            $torchInstalled = $true
            break
        }
    }

    if (-not $torchInstalled) {
        Write-Output "所有可连接的 PyTorch 下载源均安装失败，请删除 venv 文件夹后重新运行。"
        InstallFail
    }

    python -m pip install -U -I --no-deps xformers==0.0.30 @pytorchSourceArgs
    if (!($?)) {
        Write-Output "xformers 使用最快源安装失败，正在回退到 PyTorch 官方源..."
        python -m pip install -U -I --no-deps xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128
        Check "xformers 安装失败。"
    }
}

python -m pip install --upgrade -r requirements.txt
Check "训练依赖库安装失败。"

Write-Output "预下载默认 WD 打标模型 wd14-convnextv2-v2（约 388MB，首次较慢）..."
python scripts/prefetch_default_tagger.py --if-missing --tagger-models-dir "$Env:MIKAZUKI_TAGGER_MODELS_DIR"
if ($LASTEXITCODE -ne 0) {
    Write-Output "警告: 默认打标模型预下载失败，可在启动后于「打标」页首次使用时自动下载。"
}

Write-Output "安装完成"
Write-Output ""
Write-Output "可选：运行 install_flash_attn.bat 启用 Flash Attention 2 加速。"
Read-Host | Out-Null
