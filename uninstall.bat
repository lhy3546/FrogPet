@echo off
title FrogPet Uninstaller
echo ================================================
echo    FrogPet desktop frog - uninstall
echo ================================================
echo.
echo This will:
echo   1. Kill the running FrogPet.exe process
echo   2. Delete the autostart entry
echo      HKCU\Software\Microsoft\Windows\CurrentVersion\Run\FrogPet
echo   3. Delete the program folder %%LOCALAPPDATA%%\FrogPet
echo.
set /p CONF=Continue? (Y/N):
if /i not "%CONF%"=="Y" goto :cancel

taskkill /f /im FrogPet.exe >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v FrogPet /f >nul 2>&1
rd /s /q "%LOCALAPPDATA%\FrogPet" >nul 2>&1

echo.
echo [Done] Autostart entry and program files removed.
echo If this script was inside the FrogPet folder,
echo please delete the remaining folder manually.
pause
exit /b 0

:cancel
echo Cancelled. Nothing was changed.
pause
exit /b 0
