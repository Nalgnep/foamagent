@echo off
chcp 65001 >nul
REM ============================================================
REM  在 Windows 上把 S7CommPlus 网关打成单个 exe: dist\s7gateway.exe
REM  必须在 Windows 上运行 -- PyInstaller 不能在 Linux 上交叉
REM  编译出 Windows exe,反过来也一样。
REM  用法: 双击本文件,或在项目根目录执行 gateway\build_exe.bat
REM  要求: 已安装 Python 3.11/3.12 64 位,并已加入 PATH。
REM ============================================================
setlocal
cd /d %~dp0
cd ..

if not exist .venv-gateway\Scripts\python.exe (
    echo [1/4] 创建虚拟环境 .venv-gateway ...
    python -m venv .venv-gateway
    if errorlevel 1 (
        echo 创建虚拟环境失败,请确认 python 已安装并加入 PATH。
        pause
        exit /b 1
    )
)

echo [2/4] 安装依赖 ...
call .venv-gateway\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r gateway\requirements.txt
pip install -r gateway\requirements-build.txt
if errorlevel 1 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

echo [3/4] 打包 ...
pyinstaller --clean --noconfirm gateway\s7gateway.spec
if errorlevel 1 (
    echo 打包失败。
    pause
    exit /b 1
)

echo [4/4] 复制可编辑的点表到 exe 旁边 ...
copy /Y gateway\points.json dist\points.json >nul
copy /Y gateway\README.md dist\README-gateway.md >nul

echo.
echo 打包完成: dist\s7gateway.exe
echo 自测（模拟 PLC,无需真机）:
echo   dist\s7gateway.exe --mock --read-all
dist\s7gateway.exe --mock --read-all
if errorlevel 1 (
    echo 自测失败。
    pause
    exit /b 1
)
echo.
echo 自测通过。接真机前先跑 dist\s7gateway.exe --browse 核对符号名。
pause
