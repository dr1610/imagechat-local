$ErrorActionPreference = 'Stop'
function Assert-AppEnvironment {
    $envRoot=Join-Path $PSScriptRoot '.venv'
    foreach ($part in @('.venv','.venv\Scripts','.venv\Scripts\python.exe','.venv\pyvenv.cfg')) {
        $item=Get-Item -LiteralPath (Join-Path $PSScriptRoot $part) -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked Python environments are not allowed.' }
    }
    $python=Join-Path $envRoot 'Scripts\python.exe'
    & $python -I (Join-Path $PSScriptRoot 'environment_check.py') $envRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python environment is not isolated. No packages were installed.' }
}
