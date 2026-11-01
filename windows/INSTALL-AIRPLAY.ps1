# Install only the official jqssun AirPlay Server release; keep the current Home.
param(
    [Parameter(Mandatory = $true)][string]$TvHost,
    [string]$AdbPath = '.\adb.exe',
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$package = 'io.github.jqssun.airplay'
$release = 'https://github.com/jqssun/android-airplay-server/releases/download/v0.0.36/app-release.apk'
$expected = 'b8c7c595ed93f91562feedce92c27800f08f9c84df424f6ac2045e82324cf2a4'
if ($TvHost -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw 'Pass the TV IPv4 address without a port.' }
$download = Join-Path $PSScriptRoot 'airplay-download'
New-Item -ItemType Directory -Path $download -Force | Out-Null
$apk = Join-Path $download 'airplay-v0.0.36.apk'
# Enable TLS 1.2 for Windows PowerShell 5.1 without disabling certificate checks.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path -LiteralPath $apk)) {
    Invoke-WebRequest -UseBasicParsing -Uri $release -OutFile $apk
}
if ((Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    throw 'APK checksum mismatch. Nothing installed. Keep the file for diagnosis; do not use it.'
}
Write-Host "Verified official release file: $apk"
if (-not $Install) {
    Write-Host 'Download/check only. Add -Install to install this receiver and configure it.'
    exit 0
}
$AdbPath = (Resolve-Path -LiteralPath $AdbPath).Path
function Invoke-Adb {
    $out = & $AdbPath -s "${TvHost}:5555" @args
    if ($LASTEXITCODE -ne 0) { throw "ADB failed: $($args -join ' ')" }
    $out
}
& $AdbPath connect "${TvHost}:5555"
if ($LASTEXITCODE -ne 0 -or (Invoke-Adb get-state) -ne 'device') { throw 'Accept ADB authorisation on the TV.' }
$sdkText = ((Invoke-Adb shell getprop ro.build.version.sdk) -join '').Trim()
$sdk = 0
if (-not [int]::TryParse($sdkText, [ref]$sdk) -or $sdk -lt 23) { throw 'Android API 23 or newer is required.' }
$abis = ((Invoke-Adb shell getprop ro.product.cpu.abilist) -join '').Trim() -split ','
if (-not @($abis | Where-Object { $_ -in @('armeabi-v7a', 'arm64-v8a', 'x86_64') }).Count) { throw 'Device ABI is not supported by this release.' }
$beforeHome = (Invoke-Adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME) -join "`n"
$result = (Invoke-Adb install -r $apk) -join "`n"
Write-Host $result
if ($result.Trim() -notmatch '(?m)^Success\s*$') { throw 'Installation did not report Success. No fallback or uninstall will be attempted.' }
if (((Invoke-Adb shell pm path --user 0 $package) -join "`n") -notmatch '(?m)^package:') { throw 'Installed package not found for user 0.' }
$start = (Invoke-Adb shell am start -W -n "$package/.MainActivity") -join "`n"
if ($start -notmatch 'Status: ok' -or $start -match '(?m)^Error') { throw "Receiver did not open: $start" }
$settings = [ordered]@{
    'server_name' = 'TCL-AirPlay'
    'auto_start' = 'true'
    'boot_auto_start' = 'true'
    'run_in_background' = 'true'
    'advertise_mirroring' = 'true'
    'advertise_video' = 'true'
    'advertise_audio' = 'true'
}
foreach ($entry in $settings.GetEnumerator()) {
    $answer = (Invoke-Adb shell am broadcast -n "$package/.SettingsReceiver" -a "$package.SET_SETTING" --es key $entry.Key --es value $entry.Value) -join "`n"
    if ($answer -notmatch 'result=-1\b' -or $answer -match 'Permission Denial|SecurityException|(?m)^Error') {
        throw "App installed, but setting $($entry.Key) was not confirmed: $answer"
    }
}
$afterHome = (Invoke-Adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME) -join "`n"
if ($beforeHome -ne $afterHome) { Write-Warning 'Default Home changed during installation. Share both outputs before changing launchers.'; Write-Host $beforeHome; Write-Host $afterHome }
Write-Host 'AirPlay Server installed. Receiver name: TCL-AirPlay.'
Write-Host 'Test iPhone Screen Mirroring, Mac Screen Mirroring, then music/video from the same home network.'
Write-Host 'For automatic foreground launch, open receiver Settings and enable Launch on connect; Android may request Display over other apps.'
Write-Host 'DRM video is not supported. Discovery, audio/video and restart behaviour still require testing on the actual TV.'
