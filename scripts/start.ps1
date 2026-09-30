param([switch]$Demo, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop first.' }
    docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and try again.' }
    if ($Demo) {
        docker compose -f docker-compose.demo.yml config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Demo Compose configuration is invalid.' }
        if (-not $CheckOnly) {
            docker compose -f docker-compose.demo.yml up --build --detach
            if ($LASTEXITCODE -ne 0) { throw 'Demo startup failed.' }
            Write-Host 'Synthetic demo: http://localhost:8081/demo (DEMO_PORT can override the port).'
        }
        return
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        if ($CheckOnly) { throw 'No .env file found. Run scripts/start.ps1 to initialize it.' }
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $example = Get-Content -LiteralPath '.env.example' -Raw
        $example.Replace('replace-with-a-random-64-character-hex-value-before-deploying', $secret) |
            Set-Content -LiteralPath '.env' -Encoding utf8
        Write-Host 'Initialized .env with a private JWT signing key.'
    }
    $configText = Get-Content -LiteralPath '.env' -Raw
    if ($configText -match 'JWT_SECRET_KEY=(?:replace-with|change-me)') {
        throw 'Replace the placeholder JWT_SECRET_KEY in .env with a unique random secret.'
    }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid.' }
    if (-not $CheckOnly) {
        docker compose up --build --detach --wait --wait-timeout 180
        if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Inspect docker compose logs backend celery-worker celery-beat.' }
        Write-Host 'Application: http://localhost:8080; synthetic demo: http://localhost:8080/demo'
        Write-Host 'HTTP_PORT in .env can override the port. First real inference downloads models.'
    }
} finally { Pop-Location }
