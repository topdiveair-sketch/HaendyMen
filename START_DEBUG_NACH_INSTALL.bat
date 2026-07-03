@echo off
chcp 65001 >nul
title Zuhause am Bach OS V32.4 - Debug Start
set "APPDIR=%USERPROFILE%\Zuhause_am_Bach_OS_V32_4"
cd /d "%APPDIR%"
echo Starte Debug...
echo Ordner: %CD%
echo.
call START_MANAGER.bat
echo.
echo Programm beendet.
pause
