@echo off
cd /d "%~dp0"
python mimic_etl.py %*
set "etl_status=%errorlevel%"
pause
exit /b %etl_status%
