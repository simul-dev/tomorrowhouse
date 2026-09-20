$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $projectRoot
try {
    & '.\.venv\Scripts\python.exe' -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    Push-Location -LiteralPath 'frontend'
    try {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
    } finally { Pop-Location }
} finally { Pop-Location }
