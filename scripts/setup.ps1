param([switch]$WithBrowserTests)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    Push-Location -LiteralPath 'frontend'
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    if ($WithBrowserTests) {
        & '.\.venv\Scripts\python.exe' -m pip install -r requirements-browser.txt
        if ($LASTEXITCODE -ne 0) { throw 'Browser test dependency installation failed.' }
        & '.\.venv\Scripts\python.exe' -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed.' }
    }
    Write-Host 'Setup complete. Run: .\scripts\start.ps1'
} finally { Pop-Location }
