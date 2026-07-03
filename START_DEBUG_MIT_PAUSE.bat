@echo off
cd /d "%~dp0"
title DEBUG Zuhause am Bach OS V32.4 BETA
python -m pip install -r requirements.txt
python zuhause_am_bach_os_v300_foundation.py
pause
