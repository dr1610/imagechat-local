param([switch]$NoBrowser,[int]$Port=8791)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Safety.ps1')
Assert-AppEnvironment
$mutex=New-Object Threading.Mutex($false, ('Local\ImageChatLocalPort'+$Port))
$held=$false
try {
try { $held=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $held=$true }
if (!$held) { throw 'Another launcher is starting this port. Wait for it to finish.' }
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run Setup.bat first.' }
$url="http://127.0.0.1:$Port"
$probe=New-Object Net.Sockets.TcpClient
try { $occupied=$probe.ConnectAsync('127.0.0.1',$Port).Wait(1000) -and $probe.Connected } catch { $occupied=$false } finally { $probe.Dispose() }
if ($occupied) { throw "Port $Port is already in use. No process was stopped. Open the running app or select a different port." }
$data=Join-Path $PSScriptRoot 'data'
& $python -B (Join-Path $PSScriptRoot 'runtime_lock.py')
if ($LASTEXITCODE -ne 0) { throw 'Data is in use. No ComfyUI startup was attempted.' }
New-Item -ItemType Directory -Force -Path $data | Out-Null
if (Test-Path -LiteralPath (Join-Path $data 'comfy-launch.json')) {
    & (Join-Path $PSScriptRoot 'Ensure-ComfyUI.ps1') -AppRoot $PSScriptRoot
}
# Without auto-start configuration, open settings even when ComfyUI is offline.
$arguments='-B "'+(Join-Path $PSScriptRoot 'server.py')+'" --port '+$Port+' --data-dir "'+$data+'"'
$stamp=[guid]::NewGuid().ToString('N')
$child=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $data "server.$stamp.stdout.log") -RedirectStandardError (Join-Path $data "server.$stamp.stderr.log") -PassThru
for ($attempt=0;$attempt -lt 40;$attempt++) {
    Start-Sleep -Milliseconds 300
    if ($child.HasExited) { throw 'Server exited. Check the newest data/server.*.stderr.log. Existing processes were not stopped.' }
    try {
        $health=Invoke-RestMethod "$url/api/health" -TimeoutSec 2
        if ($health.application -eq 'ImageChat Local') {
            if (!$NoBrowser) { Start-Process $url }
            exit 0
        }
    } catch {}
}
throw 'Application startup failed. Check data/server.stderr.log.'
} finally { if ($held) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
