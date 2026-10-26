# Runs every tests/check_*.py headless in Blender and summarises tests/_out/*.txt.
# Usage: .\tests\run.ps1 [-Blender <path to blender.exe>] [check_lods ...]
param(
    [string]$Blender = $env:BLENDER,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Only
)

if (-not $Blender) {
    $onPath = Get-Command blender -ErrorAction SilentlyContinue
    $store = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WindowsApps\BlenderFoundation.Blender_*\blender-launcher.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($onPath) { $Blender = $onPath.Source } elseif ($store) { $Blender = $store.FullName }
    else { Write-Error "Blender not found: pass -Blender or set `$env:BLENDER"; exit 2 }
}

$here = $PSScriptRoot
$checks = Get-ChildItem "$here\check_*.py" | Where-Object { -not $Only -or $Only -contains $_.BaseName }
$failed = $false
foreach ($check in $checks) {
    $out = Join-Path $here "_out\$($check.BaseName).txt"
    Remove-Item $out -ErrorAction SilentlyContinue  # a stale file from a run that didn't start would read as a pass
    # Start-Process -Wait: the Microsoft Store launcher returns before Blender finishes otherwise
    Start-Process $Blender -ArgumentList '-b', '--factory-startup', '--python', "`"$($check.FullName)`"" -Wait -WindowStyle Hidden
    if (-not (Test-Path $out)) { "$($check.BaseName): NO OUTPUT"; $failed = $true; continue }
    $lines = Get-Content $out
    $pass = ($lines | Select-String '^PASS').Count
    $fail = $lines | Select-String '^FAIL|EXCEPTION'
    $done = $lines[-1] -eq 'DONE'
    "$($check.BaseName): $pass passed, $($fail.Count) failed$(if (-not $done) { ', did not finish' })"
    $fail | ForEach-Object { "    $_" }
    if ($fail -or -not $done) { $failed = $true }
}
if ($failed) { exit 1 }
