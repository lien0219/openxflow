@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
if errorlevel 1 (
  echo.
  echo OpenXFlow development command failed.
  pause
)
endlocal
