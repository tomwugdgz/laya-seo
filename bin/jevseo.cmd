@echo off
REM Windows launcher for jev-seo. Uses the repo-local .venv and sets the GTK3 runtime path.
setlocal
set "HERE=%~dp0"
set "VENV=%HERE%..\.venv"

if not exist "%VENV%\Scripts\python.exe" (
  echo [jevseo] venv not found at %VENV%
  echo [jevseo] create it with: py -3.13 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

REM WeasyPrint on Windows needs the GTK3 runtime on PATH.
if exist "C:\Program Files\GTK3-Runtime Win64\bin" (
  if "%PATH%"=="" (
    set "PATH=C:\Program Files\GTK3-Runtime Win64\bin;%PATH%"
  ) else (
    set "PATH=C:\Program Files\GTK3-Runtime Win64\bin;%PATH%"
  )
)

set "PYTHONPATH=%HERE%..;%PYTHONPATH%"
"%VENV%\Scripts\python.exe" -m jevseo %*
