# Wrapper around the original CleanYourTV tools, which retain their Home guards
# and recovery records. Run from the extracted Windows kit, not from the source repo.
param(
    [Parameter(Mandatory = $true)][string]$TvHost,
    [Parameter(Mandatory = $true)][string]$AdbPath,
    [ValidateSet('Inspect', 'Launcher', 'Clean', 'Restore')][string]$Mode = 'Inspect'
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$root = $PSScriptRoot
$upstream = Join-Path $root 'cleanyourtv'
$profile = Join-Path $root 'profile\apps-to-disable.txt'
$AdbPath = (Resolve-Path -LiteralPath $AdbPath).Path
if (-not (Test-Path -LiteralPath $upstream)) { throw 'Extract the complete Windows kit first.' }
if ($TvHost -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw 'Pass the TV IPv4 address, without a port.' }
$env:TV_HOST = $TvHost
$env:TV_PORT = '5555'
$env:TV_ADB_BINARY = $AdbPath
foreach ($name in @('FORCE_HOME', 'FORCE_SETUPWRAITH', 'TVINPUT_ALLOW', 'HANDLERS_ALLOW')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw "Safety override $name is set. Open a fresh PowerShell without overrides." }
}

function Invoke-Adb {
    $out = & $AdbPath -s "${TvHost}:5555" @args
    if ($LASTEXITCODE -ne 0) { throw "ADB failed: $($args -join ' ')" }
    $out
}

# Do not change global Python or install anything on the TV to run these tools.
$py = Join-Path $upstream 'tools\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $upstream 'tools\venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $upstream 'tools\venv')
    } else { throw 'Install Python 3 from python.org, then run this command again.' }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $py)) { throw 'Python venv creation failed.' }
}
& $py -m pip install -r (Join-Path $upstream 'tools\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed. No TV changes made.' }

function Invoke-Python {
    & $py -I @args
    if ($LASTEXITCODE -ne 0) { throw "CleanYourTV failed: $($args -join ' ')" }
}
$tv = Join-Path $upstream 'tools\tv.py'
& $AdbPath connect "${TvHost}:5555"
if ($LASTEXITCODE -ne 0) { throw 'ADB connect failed.' }
if ((Invoke-Adb get-state) -ne 'device') { throw 'Accept the ADB authorisation on the television.' }

function Save-State {
    $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $dir = Join-Path $root ("backup\" + $stamp)
    New-Item -ItemType Directory -Path $dir | Out-Null
    $commands = [ordered]@{
        'packages.txt' = 'pm list packages -f'
        'disabled.txt' = 'pm list packages -d'
        'properties.txt' = 'getprop'
        'settings-system.txt' = 'settings list system'
        'settings-global.txt' = 'settings list global'
        'settings-secure.txt' = 'settings list secure'
        'home.txt' = 'cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME'
    }
    foreach ($entry in $commands.GetEnumerator()) {
        Invoke-Python $tv $entry.Value | Out-File -Encoding utf8 (Join-Path $dir $entry.Key)
    }
    $audit = Join-Path $dir 'advertising-candidates.txt'
    foreach ($package in @('com.tcl.bi', 'com.tcl.logkit', 'com.tcl.partnercustomizer',
        'com.tcl.waterfall.overseas', 'com.tcl.tv.tclhome_passive', 'com.tcl.esticker',
        'com.tcl.channelplus', 'com.tcl.overseasappshow')) {
        "PACKAGE: $package" | Out-File -Encoding utf8 -Append $audit
        Invoke-Python $tv "dumpsys package $package" | Out-File -Encoding utf8 -Append $audit
    }
    Write-Host "Local state backup: $dir. Keep private; this is not a firmware/data image."
}

function Assert-NewHome {
    $homeNow = (Invoke-Python $tv 'cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME') -join "`n"
    if ($homeNow -notmatch '(?m)^com\.gathin\.tvhome/') { throw 'CleanYourTV is not the default Home. Stop and share the error.' }
    Invoke-Adb shell input keyevent KEYCODE_HOME | Out-Host
    Start-Sleep -Seconds 2
    $activity = (Invoke-Python $tv 'dumpsys activity activities') -join "`n"
    $focused = @($activity -split '\r?\n' | Where-Object { $_ -match 'mResumedActivity|topResumedActivity|mFocusedApp' }) -join "`n"
    Write-Host $focused
    if ($focused -notmatch 'com\.gathin\.tvhome/[^\s}]*MainActivity') { throw 'New Home is not visibly resumed. Do not disable anything else.' }
}

if ($Mode -eq 'Restore') {
    # Never fall back to enabling an entire list if the original record is lost.
    $recordCheck = "import sys,os; sys.path.insert(0,sys.argv[1]); import recovery; p=recovery.find_record(sys.argv[2],os.environ.get('TV_HOST')); assert p.exists(), 'Original recovery record missing; stop and recover the backup first'; recovery.load_record(p)"
    Invoke-Python -c $recordCheck (Join-Path $upstream 'tools') $profile
    # The upstream record was created before Launcher, so restore can recover
    # the previous Home as well as the original per-package states.
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $upstream 'tools\restore.ps1') -TvHost $TvHost -Stock com.google.android.apps.tv.launcherx $profile
    if ($LASTEXITCODE -ne 0) { throw 'Restore incomplete. Keep ADB enabled and share the error.' }
    Write-Host 'Restore commands completed. Press physical Home and test the stock screen.'
    exit 0
}

Save-State
$installed = (Invoke-Python $tv 'pm list packages --user 0') -join "`n"
foreach ($package in @('com.vk.tv', 'com.google.android.youtube.tv', 'com.happproxy', 'ru.kinopoisk.tv')) {
    if ($installed -notmatch ('(?m)^package:' + [regex]::Escape($package) + '\s*$')) { throw "Required app missing: $package" }
}

if ($Mode -eq 'Inspect') {
    Invoke-Python $tv --probe
    Invoke-Python $tv 'cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME'
    Write-Host 'Inspection completed. No TV applications or settings changed.'
    exit 0
}

if ($Mode -eq 'Launcher') {
    $apk = Join-Path $upstream 'launcher\app\build\outputs\apk\release\app-release.apk'
    $manifest = Get-Content -LiteralPath (Join-Path $root 'build.json') -Raw | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.apk_sha256) { throw 'APK checksum mismatch. Nothing installed.' }
    # Record the original Home before the upstream installer can change it.
    Invoke-Python (Join-Path $upstream 'tools\recovery.py') --save $profile
    $oldSkip = $env:SKIP_BUILD
    try {
        $env:SKIP_BUILD = '1'
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $upstream 'launcher\build-and-install.ps1') -TvHost $TvHost
        if ($LASTEXITCODE -ne 0) { throw 'Launcher installation stopped. Follow the upstream rollback/error, do not run Clean.' }
    } finally { $env:SKIP_BUILD = $oldSkip }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $upstream 'tools\theme.ps1') -TvHost $TvHost (Split-Path -Parent $profile)
    if ($LASTEXITCODE -ne 0) { throw 'Home is installed, but the four-app theme was not fully applied. Do not run Clean yet.' }
    Assert-NewHome
    $shots = Join-Path $root 'shots'
    New-Item -ItemType Directory -Path $shots -Force | Out-Null
    Invoke-Python $tv --screenshot (Join-Path $shots 'launcher.png')
    Write-Host 'Launcher installed. Test the REAL remote: Home, Settings, volume, HDMI and all four apps. Then run Mode Clean.'
    exit 0
}

Assert-NewHome
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $upstream 'tools\disable.ps1') -TvHost $TvHost $profile
if ($LASTEXITCODE -ne 0) { throw 'Cleanup stopped. Inspect the output before any retry.' }
$disabled = (Invoke-Python $tv 'pm list packages -d --user 0') -join "`n"
foreach ($package in (Get-Content -LiteralPath $profile | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_.]+$' })) {
    if ($disabled -notmatch ('(?m)^package:' + [regex]::Escape($package) + '\s*$')) { throw "Disable not confirmed: $package" }
}
# Android persists package settings asynchronously; don't reboot immediately.
Start-Sleep -Seconds 15
Write-Host $disabled
Write-Host 'Seven entertainment apps disabled. No firmware flashed or packages uninstalled. Test apps, then reboot manually and test Home again.'
