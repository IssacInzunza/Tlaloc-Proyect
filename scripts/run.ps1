param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Install the Python environment first; see README.md.' }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    try {
        & npm ci --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Write-Host "Tláloc: http://127.0.0.1:$Port (Ctrl+C to stop)"
& $pythonPath -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $Port --no-access-log
exit $LASTEXITCODE
