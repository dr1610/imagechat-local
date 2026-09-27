param([Parameter(Mandatory=$true)][string]$OldFolder)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Safety.ps1')
Assert-AppEnvironment
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B (Join-Path $PSScriptRoot 'import_data.py') $OldFolder
if ($LASTEXITCODE -ne 0) { throw 'Import stopped. The original data was not changed.' }
