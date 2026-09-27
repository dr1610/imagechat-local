param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'Safety.ps1')
& $Python -c 'import sys; sys.exit(sys.version_info < (3,10))'
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10+ from python.org, then run Setup again.' }
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (Test-Path -LiteralPath '.venv') { throw 'Existing incomplete .venv found. Use a fresh application folder; nothing was overwritten.' }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the application virtual environment.' }
}
Assert-AppEnvironment
& '.\.venv\Scripts\python.exe' -I environment_check.py --dependency
if ($LASTEXITCODE -eq 0) { Write-Host 'Dependencies already installed; no changes needed.'; exit 0 }
if (Test-Path -LiteralPath 'data\.instance.lock') {
    & '.\.venv\Scripts\python.exe' -B runtime_lock.py
    if ($LASTEXITCODE -ne 0) { throw 'Close the app before installing dependencies.' }
}
& '.\.venv\Scripts\python.exe' -I -m pip --isolated install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Setup complete. Run Start.bat. Existing ComfyUI environments were not changed.'
