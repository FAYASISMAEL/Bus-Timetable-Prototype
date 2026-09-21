$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program $($Arguments -join ' ')" }
}

try {
    New-Item -ItemType Directory -Force -Path .runtime\tmp | Out-Null
    $env:TEMP = Join-Path $PSScriptRoot '.runtime\tmp'
    $env:TMP = $env:TEMP
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Install Python 3.10+ from https://www.python.org/downloads/ and enable Add Python to PATH.' }
    Invoke-Checked $pythonCommand.Source @('-c', 'import sys; print(sys.version); sys.exit(0 if sys.version_info >= (3,10) else 1)')
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 20.19+ (or 22.12+) from https://nodejs.org/.' }
    Invoke-Checked 'node' @('-e', "const [a,b]=process.versions.node.split('.').map(Number); console.log(process.version); process.exit(a>22 || a===22&&b>=12 || a===20&&b>=19 ? 0 : 1)")
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'npm is missing. Reinstall Node.js and reopen PowerShell.' }
    Invoke-Checked 'npm.cmd' @('--version')
    foreach ($relative in @('backend', 'frontend')) {
        $envFile = Join-Path $PSScriptRoot "$relative\.env"
        if (-not (Test-Path -LiteralPath $envFile)) { Copy-Item -LiteralPath "$relative\.env.example" -Destination $envFile }
    }
    if (-not (Test-Path -LiteralPath 'backend\.venv\Scripts\python.exe')) {
        Invoke-Checked $pythonCommand.Source @('-m', 'venv', 'backend\.venv')
    }
    . .\backend\.venv\Scripts\Activate.ps1
    $venvPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--no-cache-dir', '--upgrade', 'pip')
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--no-cache-dir', '-r', 'backend\requirements.txt')
    Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
    try {
        $npmCache = Join-Path $PSScriptRoot '.runtime\npm-cache'
        # `npm install` is safe to rerun if a previous setup was interrupted.
        # `npm ci` removes node_modules first and can leave Vite missing when a
        # Windows process temporarily locks an esbuild/Rollup binary.
        Invoke-Checked 'npm.cmd' @('install', '--cache', $npmCache)
    } finally { Pop-Location }
    & $venvPython -c 'from backend.services.ocr_service import find_tesseract; import sys; sys.exit(0 if find_tesseract() else 1)'
    if ($LASTEXITCODE -ne 0) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host 'Attempting Tesseract installation with winget (current user scope).'
            & winget install --id UB-Mannheim.TesseractOCR --exact --scope user --accept-source-agreements --accept-package-agreements --disable-interactivity
            if ($LASTEXITCODE -ne 0) { Write-Warning 'Automatic Tesseract installation was not available. See the manual instructions below.' }
        }
        Write-Host 'Manual installation: https://github.com/UB-Mannheim/tesseract/wiki'
        Write-Host 'Or: winget install --id UB-Mannheim.TesseractOCR --exact'
        Write-Host 'Set TESSERACT_CMD in backend/.env if Tesseract is installed outside the standard location.'
    }
    # Report every missing service; download language data without modifying Program Files.
    & $venvPython scripts\check_environment.py --install-language-data
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Dependencies installed; runtime setup still needs attention. See the report above and README.md.' }
    Write-Host ''
    Write-Host 'Start: powershell -ExecutionPolicy Bypass -File .\start.ps1'
    Write-Host 'Frontend: http://localhost:5173'
} catch {
    Write-Error "Setup failed: $($_.Exception.Message)"
    exit 1
}
