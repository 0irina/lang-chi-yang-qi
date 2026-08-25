# dist watchdog: auto-resume on any exit until done flag appears
# IMPORTANT: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less
# UTF-8 as ANSI and mangles any non-ASCII literal (e.g. the Chinese dir name).
# The project dir is located either via the current working dir or by wildcard.
$py = "D:\ProgramData\anaconda3\python.exe"
$base = $null
if (Test-Path ".\solver\dist_pass.py") {
    $base = (Resolve-Path ".\solver").Path
}
if (-not $base) {
    $f = Get-Item "D:\*\solver\dist_pass.py" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($f) { $base = $f.Directory.FullName }
}
if (-not $base) {
    Add-Content "D:\watchdog_error.txt" "cannot locate solver dir"
    exit 1
}
while ($true) {
    & $py -u "$base\dist_pass.py" --resume *>> "$base\dist_pass_log.txt"
    if (Test-Path "$base\tt\dist_pass_done.flag") {
        Add-Content "$base\dist_pass_log.txt" "watchdog: done flag found, exit"
        break
    }
    Add-Content "$base\dist_pass_log.txt" "watchdog: process exited, retry in 10s"
    Start-Sleep -Seconds 10
}
