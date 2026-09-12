$ErrorActionPreference = "SilentlyContinue"
$proj = "C:\Users\PRITHVIRAJ\Documents\Default Project\jsamadhan"
$cf = "C:\Users\PRITHVIRAJ\AppData\Local\Cloudflared\cloudflared.exe"
$outlog = Join-Path $proj "tunnel_out.log"
$errlog = Join-Path $proj "tunnel_err.log"
$urlfile = Join-Path $proj "public_url.txt"

# make sure the site is up first
Start-Sleep -Seconds 10
$up = $false
for ($i = 0; $i -lt 6; $i++) {
    try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:5000/" -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -eq 200) { $up = $true; break } } catch {}
    Start-Sleep -Seconds 5
}
if (-not $up) {
    Start-Process -FilePath "pythonw.exe" -ArgumentList (Join-Path $proj "run_server.py") -WorkingDirectory $proj -WindowStyle Hidden
    Start-Sleep -Seconds 10
}

# stop any previous cloudflared from this script so we get a fresh URL
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# start the quick tunnel
Remove-Item $outlog, $errlog -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $cf -ArgumentList "tunnel", "--url", "http://127.0.0.1:5000" `
    -RedirectStandardOutput $outlog -RedirectStandardError $errlog -WindowStyle Hidden -PassThru

# wait for the public url to appear (cloudflared can print it to either log)
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    foreach ($log in @($outlog, $errlog)) {
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches
            if ($m) { $url = $m.Matches[0].Value; break }
        }
    }
    if ($url) { break }
    if ($p.HasExited) { break }
}
if ($url) {
    Set-Content -Path $urlfile -Value $url
} else {
    Set-Content -Path $urlfile -Value ("tunnel failed - see " + $errlog)
}