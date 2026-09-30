$ErrorActionPreference = 'Stop'
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw 'Install cloudflared first: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/'
}
$null = Invoke-WebRequest -UseBasicParsing 'http://localhost:8080/api/v1/health' -TimeoutSec 10
Write-Host 'Starting a temporary public HTTPS address. Open the printed URL on both devices.'
Write-Host 'Keep Docker running. Press Ctrl+C here to stop this tunnel.'
cloudflared tunnel --url http://localhost:8080 --no-autoupdate
