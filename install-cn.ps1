$Env:HF_HOME = "huggingface"
$Env:MIKAZUKI_TAGGER_MODELS_DIR = "tagger-models"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
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

$PackageInstallRetriesPerSource = 2

function Get-PipResumeRetriesArgs {
    # --resume-retries needs pip >= 23.1. A venv created by python 3.10's
    # ensurepip ships pip 23.0.1, which rejects the option during argument
    # parsing (exit 2, before any network access), so every install attempt
    # fails identically no matter the mirror. Probe instead of assuming.
    if ($null -ne $script:PipResumeRetriesArgs) {
        return $script:PipResumeRetriesArgs
    }
    $script:PipResumeRetriesArgs = @()
    # No `Select-Object -First 1` here: it stops the upstream pipeline, which
    # leaves $LASTEXITCODE at -1 and makes the probe look like a failure.
    $pipVersion = (python -m pip --version 2>$null) -join ' '
    if ($LASTEXITCODE -eq 0 -and $pipVersion -match 'pip\s+(\d+)\.(\d+)') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -gt 23 -or ($major -eq 23 -and $minor -ge 1)) {
            $script:PipResumeRetriesArgs = @("--resume-retries", "5")
        } else {
            Write-Host ("检测到 pip {0}.{1}，不支持 --resume-retries，已跳过该参数。" -f $major, $minor)
        }
    }
    return $script:PipResumeRetriesArgs
}

function Invoke-PipInstallWithRetries {
    param (
        [string]$Label,
        [string[]]$PackageArgs,
        $Source,
        [int]$RetriesPerSource
    )

    # Everything this function emits must go to the host, never to its output
    # stream: PowerShell returns the whole stream, so a single stray line turns
    # `return $false` into @(line, $false) -- a non-empty array, which is truthy.
    # That is how `if (-not (Invoke-PipInstallWithRetries ...))` stopped firing
    # and a run where all 15 pip attempts failed still printed "安装完成",
    # exited 0 and left the user an empty venv.
    # Two separate sources pollute it, and both have to be handled:
    #   - Write-Output for the retry notice (use Write-Host)
    #   - pip's own stdout, because a native command's stdout is the output
    #     stream too (pipe it to Out-Host)
    $sourceArgs = Get-PipSourceArgs $Source
    $resumeArgs = @(Get-PipResumeRetriesArgs)
    $installed = $false
    for ($attempt = 1; $attempt -le $RetriesPerSource; $attempt++) {
        if ($attempt -gt 1) {
            Write-Host ("{0} 网络波动，继续使用当前源重试 ({1}/{2}): {3}" -f $Label, $attempt, $RetriesPerSource, $Source.Name)
        }

        python -m pip install --retries 5 --timeout 60 @resumeArgs @PackageArgs @sourceArgs | Out-Host
        if ($LASTEXITCODE -eq 0) {
            $installed = $true
            break
        }
    }

    return $installed
}

function Install-PipUpgrade {
    # An explicit lower bound is required: a bare `--upgrade pip` resolves to
    # "Requirement already satisfied" and silently no-ops whenever the configured
    # mirror's index does not expose a newer pip.
    Write-Output "升级 venv 内的 pip (>=23.1)..."
    python -m pip install --upgrade "pip>=23.1" 2>&1 | Write-Host
    if ($LASTEXITCODE -eq 0) { return }

    Write-Host "镜像源升级 pip 失败，回退官方源 pypi.org 重试..."
    python -m pip install --upgrade "pip>=23.1" -i https://pypi.org/simple 2>&1 | Write-Host
    if ($LASTEXITCODE -eq 0) { return }

    Write-Output "警告: pip 升级失败，将以当前 pip 版本继续安装。"
    Write-Output "      若后续安装报 'no such option'，请手动执行:"
    Write-Output "      venv\Scripts\python.exe -m pip install --upgrade `"pip>=23.1`" -i https://mirrors.aliyun.com/pypi/simple/"
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

Install-PipUpgrade

Write-Output "安装 GUI 依赖 (已进行国内加速，如在国外无法使用加速源请换用 install.ps1 脚本)"
$requirementsSource = @{
    Name = "Python 镜像源"
    Mode = "index-url"
    Url = $Env:PIP_INDEX_URL
}
if (-not (Invoke-PipInstallWithRetries -Label "GUI 依赖" -PackageArgs @("--upgrade", "-r", "requirements.txt") -Source $requirementsSource -RetriesPerSource $PackageInstallRetriesPerSource)) {
    Write-Output "GUI 依赖库安装失败。"
    InstallFail
}

Write-Output "预下载默认 WD 打标模型 wd14-convnextv2-v2（约 388MB，首次较慢）..."
python scripts/prefetch_default_tagger.py --if-missing --tagger-models-dir "$Env:MIKAZUKI_TAGGER_MODELS_DIR"
if ($LASTEXITCODE -ne 0) {
    Write-Output "警告: 默认打标模型预下载失败，可在启动后于「打标」页首次使用时自动下载。"
}

Write-Output "安装完成"
Write-Output ""
Write-Output "注意：训练依赖（torch、sd-scripts 训练栈）不再随本环境安装，"
Write-Output "请启动后在「设置 -> 训练引擎」页安装所需训练引擎。"
Read-Host | Out-Null
