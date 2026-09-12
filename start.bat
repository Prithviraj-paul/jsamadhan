@echo off
title Jharkhand Samadhan Server
cd /d "%~dp0"
echo Starting Jharkhand Samadhan...
echo Open http://127.0.0.1:5000 in your browser when ready.
echo Press Ctrl+C to stop the server.
python run_server.py
pause