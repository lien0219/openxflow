[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "install", "start", "help", "backend", "frontend")]
    [string]$Action = "all",

    [string]$PythonVersion = "3.12",
    [int]$BackendPort = 7860,
    [int]$FrontendPort = 3000,
    [string]$ListenHost = "0.0.0.0",
    [switch]$SkipPreCommit,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "src\frontend"

if ($env:OPENXFLOW_PYTHON_VERSION -and -not $PSBoundParameters.ContainsKey("PythonVersion")) {
    $PythonVersion = $env:OPENXFLOW_PYTHON_VERSION
}
if ($env:OPENXFLOW_BACKEND_PORT -and -not $PSBoundParameters.ContainsKey("BackendPort")) {
    $BackendPort = [int]$env:OPENXFLOW_BACKEND_PORT
}
if ($env:OPENXFLOW_FRONTEND_PORT -and -not $PSBoundParameters.ContainsKey("FrontendPort")) {
    $FrontendPort = [int]$env:OPENXFLOW_FRONTEND_PORT
}
if ($env:OPENXFLOW_HOST -and -not $PSBoundParameters.ContainsKey("ListenHost")) {
    $ListenHost = $env:OPENXFLOW_HOST
}

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. $InstallHint"
    }
}

function Invoke-NativeCommand {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $Command $($Arguments -join ' ')"
    }
}

function Assert-NodeVersion {
    $version = (Invoke-NativeCommandCapture -Command "node" -Arguments @("--version")).TrimStart("v")
    $parts = $version.Split(".")
    $major = [int]$parts[0]
    $minor = if ($parts.Length -gt 1) { [int]$parts[1] } else { 0 }

    if (($major -lt 20) -or ($major -eq 20 -and $minor -lt 19)) {
        throw "Node.js 20.19 or newer is required. Current version: $version"
    }
}

function Invoke-NativeCommandCapture {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    $output = & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $Command $($Arguments -join ' ')"
    }
    return ($output | Out-String).Trim()
}

function Ensure-EnvironmentFile {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        $examplePath = Join-Path $ProjectRoot ".env.example"
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $envPath
            Write-Host "Created .env from .env.example" -ForegroundColor Yellow
        }
        else {
            New-Item -Path $envPath -ItemType File | Out-Null
            Write-Host "Created an empty .env file" -ForegroundColor Yellow
        }
    }
}

function Install-ProjectDependencies {
    Write-Section "Checking development prerequisites"
    Assert-Command -Name "uv" -InstallHint "Install uv from https://docs.astral.sh/uv/getting-started/installation/."
    Assert-Command -Name "node" -InstallHint "Install Node.js 20.19 or newer from https://nodejs.org/."
    Assert-Command -Name "npm" -InstallHint "npm is normally installed together with Node.js."
    Assert-NodeVersion

    Set-Location $ProjectRoot
    Ensure-EnvironmentFile

    Write-Section "Preparing Python $PythonVersion"
    Invoke-NativeCommand -Command "uv" -Arguments @("python", "install", $PythonVersion)

    $venvPath = Join-Path $ProjectRoot ".venv"
    $windowsPython = Join-Path $venvPath "Scripts\python.exe"
    if ((Test-Path $venvPath) -and -not (Test-Path $windowsPython)) {
        Write-Warning "The existing .venv is not a Windows virtual environment. It will be recreated for Windows."
        Remove-Item -Recurse -Force $venvPath
    }

    Write-Section "Installing backend dependencies"
    Invoke-NativeCommand -Command "uv" -Arguments @(
        "sync",
        "--python", $PythonVersion,
        "--frozen",
        "--extra", "postgresql"
    )

    Write-Section "Installing frontend dependencies"
    Push-Location $FrontendRoot
    try {
        Invoke-NativeCommand -Command "npm" -Arguments @("ci")
    }
    finally {
        Pop-Location
    }

    if (-not $SkipPreCommit -and (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Write-Section "Installing pre-commit hooks"
        Invoke-NativeCommand -Command "uvx" -Arguments @("pre-commit", "install")
    }

    Write-Host ""
    Write-Host "OpenXFlow dependencies are ready." -ForegroundColor Green
}

function Test-DependenciesReady {
    $pythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $nodeModulesPath = Join-Path $FrontendRoot "node_modules"
    return (Test-Path $pythonPath) -and (Test-Path $nodeModulesPath)
}

function Start-BackendService {
    Assert-Command -Name "uv" -InstallHint "Run '.\dev.ps1 install' first."
    Set-Location $ProjectRoot
    Ensure-EnvironmentFile

    Write-Section "Starting backend on http://localhost:$BackendPort"
    Invoke-NativeCommand -Command "uv" -Arguments @(
        "run", "uvicorn",
        "--factory", "langflow.main:create_app",
        "--host", $ListenHost,
        "--port", "$BackendPort",
        "--reload",
        "--env-file", ".env",
        "--loop", "asyncio"
    )
}

function Start-FrontendService {
    Assert-Command -Name "npm" -InstallHint "Run '.\dev.ps1 install' first."
    $env:VITE_HOST = $ListenHost
    $env:VITE_PORT = "$FrontendPort"
    $env:VITE_PROXY_TARGET = "http://127.0.0.1:$BackendPort"

    Push-Location $FrontendRoot
    try {
        Write-Section "Starting frontend on http://localhost:$FrontendPort"
        Invoke-NativeCommand -Command "npm" -Arguments @("run", "start")
    }
    finally {
        Pop-Location
    }
}

function Start-DevelopmentServices {
    if (-not (Test-DependenciesReady)) {
        Write-Warning "Project dependencies are incomplete. Running the installer first."
        Install-ProjectDependencies
    }

    Ensure-EnvironmentFile

    $shellPath = (Get-Process -Id $PID).Path
    $quotedScript = '"' + $PSCommandPath + '"'

    $backendArguments = @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $quotedScript,
        "backend",
        "-PythonVersion", $PythonVersion,
        "-BackendPort", "$BackendPort",
        "-FrontendPort", "$FrontendPort",
        "-ListenHost", $ListenHost
    )

    $frontendArguments = @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $quotedScript,
        "frontend",
        "-PythonVersion", $PythonVersion,
        "-BackendPort", "$BackendPort",
        "-FrontendPort", "$FrontendPort",
        "-ListenHost", $ListenHost
    )

    Write-Section "Starting OpenXFlow development services"
    Start-Process -FilePath $shellPath -ArgumentList $backendArguments | Out-Null
    Start-Sleep -Seconds 1
    Start-Process -FilePath $shellPath -ArgumentList $frontendArguments | Out-Null

    Write-Host "Backend:  http://localhost:$BackendPort" -ForegroundColor Green
    Write-Host "Frontend: http://localhost:$FrontendPort" -ForegroundColor Green
    Write-Host "LAN:      http://<your-computer-ip>:$FrontendPort" -ForegroundColor Green
    Write-Host ""
    Write-Host "The backend and frontend are running in separate PowerShell windows."

    if (-not $NoBrowser) {
        Start-Sleep -Seconds 2
        Start-Process "http://localhost:$FrontendPort" | Out-Null
    }
}

function Show-Help {
    @"
OpenXFlow Windows development helper

Usage:
  .\dev.ps1                 Install dependencies and start backend + frontend
  .\dev.ps1 all             Same as the default action
  .\dev.ps1 install         Install project dependencies only
  .\dev.ps1 start           Start backend + frontend without reinstalling
  .\dev.ps1 help            Show this help

Common options:
  -PythonVersion 3.12
  -BackendPort 7860
  -FrontendPort 3000
  -ListenHost 0.0.0.0
  -SkipPreCommit
  -NoBrowser

Environment variable equivalents:
  OPENXFLOW_PYTHON_VERSION
  OPENXFLOW_BACKEND_PORT
  OPENXFLOW_FRONTEND_PORT
  OPENXFLOW_HOST

The existing commands such as 'make init', 'make backend', and 'make frontend'
remain supported and are not changed by this helper.
"@ | Write-Host
}

try {
    switch ($Action) {
        "install" { Install-ProjectDependencies }
        "start" { Start-DevelopmentServices }
        "all" {
            Install-ProjectDependencies
            Start-DevelopmentServices
        }
        "backend" { Start-BackendService }
        "frontend" { Start-FrontendService }
        "help" { Show-Help }
    }
}
catch {
    Write-Host ""
    Write-Host "OpenXFlow development command failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
