param([string]$WeightsDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$modelRepo = Join-Path $projectRoot 'backend/third_party/Silent-Face-Anti-Spoofing'
if (-not (Test-Path -LiteralPath $modelRepo)) {
    New-Item -ItemType Directory -Path (Split-Path $modelRepo -Parent) -Force | Out-Null
    git clone --depth 1 https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git $modelRepo
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the upstream MiniFASNet source.' }
}
$destination = Join-Path $modelRepo 'resources/anti_spoof_models'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
if ($WeightsDirectory) {
    $source = (Resolve-Path -LiteralPath $WeightsDirectory).Path
    $weights = Get-ChildItem -LiteralPath $source -Filter '*.pth' -File
    if (-not $weights) { throw 'No .pth model files found in the supplied directory.' }
    foreach ($weight in $weights) { Copy-Item -LiteralPath $weight.FullName -Destination $destination }
}
Write-Host 'MiniFASNet source prepared. Confirm model provenance and licensing before use.'
Write-Host 'Model setup and filenames are documented in docs/models.md. No weights are committed to Git.'
