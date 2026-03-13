param(
    [ValidateSet("install", "env-template", "train-fast", "train", "shadow-once", "shadow", "live", "test", "notebook")]
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
}
