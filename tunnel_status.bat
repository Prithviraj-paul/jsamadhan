@echo off
title Jharkhand Samadhan - Public URL
cd /d "%~dp0"
if not exist public_url.txt (
  echo Public URL not found - the tunnel has not started yet.
  echo It starts automatically about 30 seconds after login.
  pause
  exit /b
)
echo.
echo  Jharkhand Samadhan is live at:
echo.
set /p URL=<public_url.txt
echo      %URL%
echo.
echo  Open this link on any device with internet (works on mobile data).
echo.
pause