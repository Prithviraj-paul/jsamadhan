@echo off
:: Self-elevating firewall setup for the Jharkhand Samadhan server (port 5000).
:: Double-click this once (as long as you can click "Yes" on the UAC prompt).
setlocal
cd /d "%~dp0"
>"%TEMP%\jsamadhan_elev.js" echo var s=new ActiveXObject("WScript.Shell");s.Run("netsh advfirewall firewall add rule name=\"Jsamadhan Server 5000\" dir=in action=allow protocol=TCP localport=5000 profile=any",0,true);
cscript //nologo "%TEMP%\jsamadhan_elev.js"
del "%TEMP%\jsamadhan_elev.js"
netsh advfirewall firewall show rule name="Jsamadhan Server 5000" >nul 2>&1 && echo OK: firewall rule is active. || echo WARNING: rule not present - run this as Administrator.
endlocal