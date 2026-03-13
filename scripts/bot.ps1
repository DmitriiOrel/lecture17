param(
    [ValidateSet("install", "env-template", "train-fast", "train", "shadow-once", "shadow", "live", "test", "notebook", "docker-build", "docker-shadow-once", "docker-live-up", "docker-live-logs", "docker-live-down")]
    [string]$Action = "shadow-once",
    [string]$Config = "config/micro_near_v1_1m.json",
    [string]$ModelPath = "models/near_basis_qlearning.json",
    [string]$EnvFile = ".runtime/kucoin.env",
    [int]$Episodes = 80,
    [string]$Start = "",
    [string]$End = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $ProjectDir "run_trade_signal.py"
$VenvPython = Join-Path $ProjectDir "venv\Scripts\python.exe"

function Invoke-Checked {
    param(
        [string]$Exe,
        [string[]]$ArgList
    )
    Write-Host "> $Exe $($ArgList -join ' ')"
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Ensure-VenvPython {
    if (-not (Test-Path $VenvPython)) {
        throw "venv python not found: $VenvPython. Run: .\scripts\bot.ps1 -Action install"
    }
}

function Ensure-Docker {
    if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {
        throw "docker CLI not found in PATH. Install Docker Desktop."
    }
}

function Invoke-DockerCompose {
    param(
        [string[]]$ArgList
    )
    Push-Location $ProjectDir
    try {
        Write-Host "> docker compose $($ArgList -join ' ')"
        & docker compose @ArgList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

function Remove-DockerContainerIfExists {
    param(
        [string]$Name
    )
    $existing = (& docker ps -a --filter "name=^${Name}$" --format "{{.ID}}").Trim()
    if ($existing) {
        Write-Host "> docker rm -f $Name"
        & docker rm -f $Name | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove existing container: $Name"
        }
    }
}

switch ($Action) {
    "install" {
        $SystemPython = "python"
        if (-not (Get-Command $SystemPython -ErrorAction SilentlyContinue)) {
            throw "System python is not available in PATH."
        }
        if (-not (Test-Path $VenvPython)) {
            Invoke-Checked -Exe $SystemPython -ArgList @("-m", "venv", "venv")
        }
        Invoke-Checked -Exe $VenvPython -ArgList @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools<81")
        Invoke-Checked -Exe $VenvPython -ArgList @("-m", "pip", "install", "-r", "requirements.txt")
        Write-Host "Install complete."
    }
    "env-template" {
        $Example = Join-Path $ProjectDir "examples\kucoin.env.example"
        $Target = Join-Path $ProjectDir $EnvFile
        $TargetDir = Split-Path -Parent $Target
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        if (-not (Test-Path $Target)) {
            Copy-Item $Example $Target -Force
            Write-Host "Created: $Target"
        } else {
            Write-Host "Already exists: $Target"
        }
    }
    "train-fast" {
        Ensure-VenvPython
        if ([string]::IsNullOrWhiteSpace($Start)) { $Start = "2026-03-10T00:00:00Z" }
        if ([string]::IsNullOrWhiteSpace($End)) { $End = "2026-03-11T00:00:00Z" }
        Invoke-Checked -Exe $VenvPython -ArgList @(
            $Runner, "--mode", "train", "--episodes", "10",
            "--start", $Start, "--end", $End,
            "--config", $Config, "--model-path", $ModelPath, "--env-file", $EnvFile
        )
    }
    "train" {
        Ensure-VenvPython
        $args = @(
            $Runner, "--mode", "train", "--episodes", "$Episodes",
            "--config", $Config, "--model-path", $ModelPath, "--env-file", $EnvFile
        )
        if (-not [string]::IsNullOrWhiteSpace($Start)) { $args += @("--start", $Start) }
        if (-not [string]::IsNullOrWhiteSpace($End)) { $args += @("--end", $End) }
        Invoke-Checked -Exe $VenvPython -ArgList $args
    }
    "shadow-once" {
        Ensure-VenvPython
        Invoke-Checked -Exe $VenvPython -ArgList @(
            $Runner, "--mode", "shadow", "--once",
            "--config", $Config, "--model-path", $ModelPath, "--env-file", $EnvFile
        )
    }
    "shadow" {
        Ensure-VenvPython
        Invoke-Checked -Exe $VenvPython -ArgList @(
            $Runner, "--mode", "shadow",
            "--config", $Config, "--model-path", $ModelPath, "--env-file", $EnvFile
        )
    }
    "live" {
        Ensure-VenvPython
        Invoke-Checked -Exe $VenvPython -ArgList @(
            $Runner, "--mode", "live", "--run-real-order",
            "--config", $Config, "--model-path", $ModelPath, "--env-file", $EnvFile
        )
    }
    "test" {
        Ensure-VenvPython
        $env:PYTHONPATH = "src"
        Invoke-Checked -Exe $VenvPython -ArgList @("-m", "pytest", "tests", "-q")
    }
    "notebook" {
        Ensure-VenvPython
        Invoke-Checked -Exe $VenvPython -ArgList @("-m", "jupyter", "lab", "notebooks/lecture16_basis_rl_colab.ipynb")
    }
    "docker-build" {
        Ensure-Docker
        Push-Location $ProjectDir
        try {
            Invoke-Checked -Exe "docker" -ArgList @("build", "-t", "lecture17-kucoin-rl", ".")
        } finally {
            Pop-Location
        }
    }
    "docker-shadow-once" {
        Ensure-Docker
        New-Item -ItemType Directory -Path (Join-Path $ProjectDir ".runtime"), (Join-Path $ProjectDir "models"), (Join-Path $ProjectDir "reports"), (Join-Path $ProjectDir "logs") -Force | Out-Null
        Invoke-DockerCompose -ArgList @("run", "--rm", "near-rl-shadow-once")
    }
    "docker-live-up" {
        Ensure-Docker
        New-Item -ItemType Directory -Path (Join-Path $ProjectDir ".runtime"), (Join-Path $ProjectDir "models"), (Join-Path $ProjectDir "reports"), (Join-Path $ProjectDir "logs") -Force | Out-Null
        Remove-DockerContainerIfExists -Name "near-rl-live"
        Invoke-DockerCompose -ArgList @("up", "-d", "--build", "near-rl-live")
    }
    "docker-live-logs" {
        Ensure-Docker
        Invoke-DockerCompose -ArgList @("logs", "-f", "--tail", "100", "near-rl-live")
    }
    "docker-live-down" {
        Ensure-Docker
        Invoke-DockerCompose -ArgList @("down")
    }
}
