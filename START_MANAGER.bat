@echo off
cd /d "%~dp0"
title Zuhause am Bach OS V32.4 BETA
python -m pip install -r requirements.txt
start "" pythonw zuhause_am_bach_os_v300_foundation.py
