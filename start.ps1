$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
foreach ($relative in @('backend\.venv\Scripts\python.exe', 'backend\.env', 'frontend\.env', 'frontend\node_modules')) {
    if (-not (Test-Path -LiteralPath $relative)) { Write-Error "Missing $relative. Run setup.ps1 first."; exit 1 }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-Error 'Node.js is missing. Run setup.ps1.'; exit 1 }
& node scripts\launch.mjs dev
exit $LASTEXITCODE
