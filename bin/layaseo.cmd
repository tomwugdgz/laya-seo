@echo off
REM ============================================================
REM  laya-seo launcher (Windows)
REM  Cascade: local Laya discriminative model -> Jev cloud -> human
REM ============================================================
setlocal
title laya-seo
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [laya-seo] .venv not found. Create it with:
  echo   py -3.13 -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  echo   .venv\Scripts\pip install laya
  exit /b 1
)

REM WeasyPrint on Windows needs Pango on PATH. Provided by MSYS2 mingw64.
if exist "C:\msys64\mingw64\bin\libpango-1.0-0.dll" set "PATH=C:\msys64\mingw64\bin;%PATH%"
if exist "C:\Program Files\GTK3-Runtime Win64\bin" set "PATH=C:\Program Files\GTK3-Runtime Win64\bin;%PATH%"

set "PYTHONPATH=%CD%;%PYTHONPATH%"
set "LAYA_MODEL_DIR=%LAYA_MODEL_DIR%"
if "%LAYA_MODEL_DIR%"=="" set "LAYA_MODEL_DIR=%USERPROFILE%\laya-models\laya"

REM 把 .env 载入环境变量：Jev 端点与模型名是模块加载时读取的，
REM 而 env.py 只负责 TYPESAFE_API_KEY 这类密钥查找。
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if not "%%a"=="" set "%%a=%%b"
  )
)

.venv\Scripts\python.exe -m jevseo %*
endlocal
