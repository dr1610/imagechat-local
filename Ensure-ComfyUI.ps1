param([Parameter(Mandatory=$true)][string]$AppRoot)
$ErrorActionPreference = 'Stop'
$dataPath = Join-Path $AppRoot 'data'
$configPath = Join-Path $dataPath 'comfy-launch.json'
$settingsPath = Join-Path $dataPath 'settings.json'
$comfyUrl = 'http://127.0.0.1:8188'
if (Test-Path -LiteralPath $settingsPath) {
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    if ($settings.comfy_url) { $comfyUrl = $settings.comfy_url.TrimEnd('/') }
}
function Test-ComfyReady {
    try {
        $stats = Invoke-RestMethod "$comfyUrl/system_stats" -TimeoutSec 2
        return ($null -ne $stats.system -and $null -ne $stats.devices)
    } catch { return $false }
}
if (Test-ComfyReady) { Write-Host 'ComfyUI is already ready.'; return }
if (-not (Test-Path -LiteralPath $configPath)) { throw "ComfyUI is offline. Configure $configPath or start ComfyUI manually." }
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$uri = [uri]$comfyUrl
if ($uri.Host -notin @('127.0.0.1','localhost','::1') -or $config.url.TrimEnd('/') -ne $comfyUrl) {
    throw 'ComfyUI is offline and the configured launch URL does not match the local connection URL. Check data/comfy-launch.json and app settings.'
}
$comfyDirectory = (Resolve-Path -LiteralPath $config.directory).Path
$comfyPython = $config.python
if (-not [IO.Path]::IsPathRooted($comfyPython)) { $comfyPython = Join-Path $comfyDirectory $comfyPython }
if (-not (Test-Path -LiteralPath $comfyPython) -or -not (Test-Path -LiteralPath (Join-Path $comfyDirectory 'main.py'))) { throw 'Existing ComfyUI Python or main.py is missing. Check data/comfy-launch.json.' }
$timeout = [int]$config.timeout_seconds
if ($timeout -lt 5 -or $timeout -gt 600) { throw 'timeout_seconds must be between 5 and 600.' }
# Never start over a live listener or a process from a previous launch that is still loading.
$existing = $false
$tcp = New-Object Net.Sockets.TcpClient
try { $task = $tcp.ConnectAsync($uri.Host,$uri.Port); $existing = $task.Wait(1000) -and $tcp.Connected } catch {} finally { $tcp.Dispose() }
$pidPath = Join-Path $dataPath 'comfy-launch-process.json'
if (-not $existing -and (Test-Path -LiteralPath $pidPath)) {
    try {
        $saved = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        $prior = Get-Process -Id $saved.pid -ErrorAction Stop
        $existing = $prior.StartTime.ToUniversalTime().Ticks.ToString() -eq $saved.start_ticks
    } catch {}
}
$started = $null
if (-not $existing) {
    $arguments = @($config.arguments | ForEach-Object {
        $value = [string]$_
        if ($value.Contains('"') -or $value.Contains("`n") -or $value.EndsWith('\')) { throw 'Unsupported launch argument. Avoid quotes, newlines and trailing backslashes.' }
        '"' + $value + '"'
    }) -join ' '
    Write-Host 'Starting existing ComfyUI in the background...'
    $started = Start-Process -FilePath $comfyPython -ArgumentList $arguments -WorkingDirectory $comfyDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dataPath 'comfy-launch.stdout.log') -RedirectStandardError (Join-Path $dataPath 'comfy-launch.stderr.log') -PassThru
    @{pid=$started.Id;start_ticks=$started.StartTime.ToUniversalTime().Ticks.ToString()} | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding UTF8
} else { Write-Host 'Waiting for the existing ComfyUI process/listener...' }
$timer = [Diagnostics.Stopwatch]::StartNew()
while ($timer.Elapsed.TotalSeconds -lt $timeout) {
    if (Test-ComfyReady) { Write-Host 'ComfyUI is ready.'; return }
    if ($started -and $started.HasExited) { throw 'ComfyUI exited during startup. See data/comfy-launch.stderr.log.' }
    Start-Sleep -Milliseconds 500
}
throw 'ComfyUI did not become ready in time. No second process was started. See data/comfy-launch.stderr.log and check the configured port.'
