@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [INFO] 未检测到项目独立环境，开始创建 .venv（Python 3.10）...
    if exist "D:\Python310\python.exe" (
        "D:\Python310\python.exe" -m venv "%VENV_DIR%"
    ) else (
        py -3.10 -m venv "%VENV_DIR%"
    )
    if errorlevel 1 (
        echo [ERROR] 创建 .venv 失败，请先安装 Python 3.10。
        pause
        exit /b 1
    )
)

echo [INFO] 使用项目环境：%VENV_PY%
"%VENV_PY%" -c "import PyQt6, llama_cpp" >nul 2>nul
if errorlevel 1 (
    echo [INFO] 检测到依赖未就绪，开始安装 requirements.txt（首次会较慢）...
    set "PIP_EXTRA_INDEX_URL=https://abetlen.github.io/llama-cpp-python/whl/cpu"
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败，请检查网络或手动执行安装命令。
        pause
        exit /b 1
    )
)

"%VENV_PY%" main.py
