$ErrorActionPreference = "SilentlyContinue"
$proj = "C:\Users\PRITHVIRAJ\Documents\Default Project\jsamadhan"
$ng = "C:\Users\PRITHVIRAJ\ngrok\ngrok.exe"
$domain = "majority-bolt-rentable.ngrok-free.dev"
$outlog = Join-Path $proj "tunnel_out.log"
$errlog = Join-Path $proj "tunnel_err.log"
$urlfile = Join-Path $proj "public_url.txt"
$permanent = "https://" + $domain

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

# stop any previous tunnel agent so only one owns the domain
Get-Process ngrok, cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# start the permanent ngrok tunnel to the fixed dev domain
Remove-Item $outlog, $errlog -ErrorAction SilentlyContinue
try {
    $p = Start-Process -FilePath $ng -ArgumentList "http", "--url=$domain", "http://127.0.0.1:5000" `
        -RedirectStandardOutput $outlog -RedirectStandardError $errlog -WindowStyle Hidden -PassThru -ErrorAction Stop
    if ($null -eq $p) { throw "Start-Process returned no process object" }
} catch {
    Set-Content -Path $urlfile -Value ("tunnel start FAILED - " + $_.Exception.Message)
    exit 1
}

# wait until the public endpoint answers (browser-ua hits ngrok's interstitial; that still 200s)
$reachable = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    try { if ((Invoke-WebRequest -Uri $permanent -UseBasicParsing -TimeoutSec 6).StatusCode -eq 200) { $reachable = $true; break } } catch {}
    if ($p.HasExited) { break }
}
if ($reachable) {
    Set-Content -Path $urlfile -Value $permanent
} elseif ($p.HasExited) {
    Set-Content -Path $urlfile -Value ("tunnel exited rc=" + $p.ExitCode + " - see " + $errlog)
} else {
    Set-Content -Path $urlfile -Value $permanent
}