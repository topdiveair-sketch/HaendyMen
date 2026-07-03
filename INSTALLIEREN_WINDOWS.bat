@echo off
chcp 65001 >nul
title Zuhause am Bach OS V32.4 - Installation

echo.
echo ================================================
echo   Zuhause am Bach OS V32.4 BETA Installation
echo ================================================
echo.

set "TARGET=%USERPROFILE%\Zuhause_am_Bach_OS_V32_4"
set "ZIP=%~dp0Zuhause_am_Bach_OS_V32_4_BETA_MOBILE_SYNC_EXPORT.zip"

if not exist "%ZIP%" (
  echo FEHLER: Installations-ZIP nicht gefunden:
  echo %ZIP%
  pause
  exit /b 1
)

echo Zielordner:
echo %TARGET%
echo.

if exist "%TARGET%" (
  echo HINWEIS: Zielordner existiert bereits.
  echo Bitte Zielordner vorher umbenennen oder sichern:
  echo %TARGET%
  pause
  exit /b 1
)

mkdir "%TARGET%" >nul 2>&1

echo Entpacke Programm...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%TARGET%' -Force"

if errorlevel 1 (
  echo.
  echo FEHLER: Entpacken fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo Erstelle Desktop-Verknuepfung...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Zuhause am Bach OS V32.4.lnk'); $s.TargetPath='%TARGET%\START_MANAGER.bat'; $s.WorkingDirectory='%TARGET%'; $s.Save()"

echo.
echo Installation fertig.
echo.
echo Start:
echo Desktop-Verknuepfung Zuhause am Bach OS V32.4
echo oder:
echo %TARGET%\START_MANAGER.bat
echo.
pause
