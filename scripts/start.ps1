param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe') -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
        throw 'Run scripts\setup.ps1 first.'
    }
    $env:PYTHONUTF8 = '1'
    Write-Host "Open http://127.0.0.1:$Port (Ctrl+C to stop)"
    & '.\.venv\Scripts\python.exe' -m uvicorn backend.api:app --host 127.0.0.1 --port $Port
} finally { Pop-Location }
