param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [switch]$SkipInstall,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Quote-ForPowerShell {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $prefix = "$Key="
        if ($trimmed.StartsWith($prefix)) {
            return $trimmed.Substring($prefix.Length).Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function Start-DevWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $quotedDir = Quote-ForPowerShell $WorkingDirectory
    $quotedTitle = Quote-ForPowerShell $Title
    $windowCommand = "Set-Location -LiteralPath $quotedDir; `$Host.UI.RawUI.WindowTitle = $quotedTitle; $Command"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $windowCommand
    )
}

Write-Host "Medi dev launcher" -ForegroundColor Cyan
Write-Host "Root: $Root"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}
if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}
if (-not (Test-CommandExists "python")) {
    throw "Python was not found. Install Python and make sure 'python' is available in PATH."
}
if (-not (Test-CommandExists "npm")) {
    throw "npm was not found. Install Node.js and make sure 'npm' is available in PATH."
}

$backendEnv = Join-Path $BackendDir ".env"
$backendEnvExample = Join-Path $BackendDir ".env.example"
if (-not (Test-Path $backendEnv) -and (Test-Path $backendEnvExample)) {
    Copy-Item -LiteralPath $backendEnvExample -Destination $backendEnv
    Write-Host "Created backend .env from .env.example"
}

$frontendEnv = Join-Path $FrontendDir ".env.local"
if (-not (Test-Path $frontendEnv)) {
    @"
NEXT_PUBLIC_API_MODE=real
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$BackendPort
"@ | Set-Content -LiteralPath $frontendEnv -Encoding utf8
    Write-Host "Created frontend .env.local"
}

$databaseUrl = $env:DATABASE_URL
if (-not $databaseUrl) {
    $databaseUrl = Get-DotEnvValue -Path $backendEnv -Key "DATABASE_URL"
}
if (-not $databaseUrl) {
    throw "DATABASE_URL is required because application data is stored in PostgreSQL."
}
try {
    $databaseUri = [System.Uri]$databaseUrl
    $databaseHost = $databaseUri.Host
    $databasePort = if ($databaseUri.Port -gt 0) { $databaseUri.Port } else { 5432 }
}
catch {
    throw "DATABASE_URL is not a valid PostgreSQL URL: $databaseUrl"
}

$postgresReady = Test-NetConnection -ComputerName $databaseHost -Port $databasePort -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $postgresReady) {
    $postgresMessage = "PostgreSQL is not reachable at ${databaseHost}:${databasePort}. Start PostgreSQL first. If Docker is installed, run: cd backend; docker compose -f docker-compose.knowledge.yml up -d postgres"
    if ($CheckOnly) {
        Write-Host $postgresMessage -ForegroundColor Yellow
        exit 1
    }
    throw $postgresMessage
}

$venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$pythonCommand = if (Test-Path $venvPython) { $venvPython } else { "python" }

if (-not $SkipInstall) {
    Push-Location $BackendDir
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $pythonCommand -c "import fastapi, uvicorn, multipart, httpx, psycopg, pymilvus, fitz, jieba" *> $null
        $backendDepsReady = $LASTEXITCODE -eq 0
        $ErrorActionPreference = $previousErrorActionPreference
        if (-not $backendDepsReady) {
            Write-Host "Installing backend dependencies..."
            & $pythonCommand -m pip install -r requirements.txt
        }
    }
    finally {
        Pop-Location
    }

    $nodeModules = Join-Path $FrontendDir "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Push-Location $FrontendDir
        try {
            Write-Host "Installing frontend dependencies..."
            npm ci
        }
        finally {
            Pop-Location
        }
    }
}

if ($CheckOnly) {
    Write-Host ""
    Write-Host "Environment check completed." -ForegroundColor Green
    Write-Host "Backend command:  python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort"
    Write-Host "Frontend command: npm run dev -- --hostname 127.0.0.1 --port $FrontendPort"
    exit 0
}

$nextCache = Join-Path $FrontendDir ".next"
if (Test-Path $nextCache) {
    $resolvedCache = (Resolve-Path -LiteralPath $nextCache).Path
    $resolvedFrontend = (Resolve-Path -LiteralPath $FrontendDir).Path
    if ($resolvedCache.StartsWith($resolvedFrontend, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Removing stale Next.js cache..."
        Remove-Item -LiteralPath $resolvedCache -Recurse -Force
    }
    else {
        throw "Refusing to remove unexpected cache path: $resolvedCache"
    }
}

$quotedPython = if ($pythonCommand -eq "python") { "python" } else { "& " + (Quote-ForPowerShell $pythonCommand) }
$backendCommand = "`$env:PYTHONIOENCODING='utf-8'; $quotedPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort"
$frontendCommand = "`$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:$BackendPort'; npm run dev -- --hostname 127.0.0.1 --port $FrontendPort"

Start-DevWindow -Title "Medi Backend :$BackendPort" -WorkingDirectory $BackendDir -Command $backendCommand
Start-Sleep -Seconds 2
Start-DevWindow -Title "Medi Frontend :$FrontendPort" -WorkingDirectory $FrontendDir -Command $frontendCommand

Write-Host ""
Write-Host "Started Medi development servers." -ForegroundColor Green
Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Swagger:  http://127.0.0.1:$BackendPort/docs"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host ""
Write-Host "Close the two opened PowerShell windows to stop the servers."
