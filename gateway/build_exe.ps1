# 在 Windows 上把 S7CommPlus 网关打成单个 exe: dist\s7gateway.exe
# 必须在 Windows 上运行 -- PyInstaller 不能在 Linux 上交叉编译出 Windows exe。
# 用法: 在项目根目录执行 .\gateway\build_exe.ps1
# 要求: 已安装 Python 3.11/3.12 64 位,并已加入 PATH。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .venv-gateway\Scripts\python.exe)) {
    Write-Host "[1/4] 创建虚拟环境 .venv-gateway ..."
    python -m venv .venv-gateway
}

Write-Host "[2/4] 安装依赖 ..."
& .venv-gateway\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r gateway\requirements.txt
pip install -r gateway\requirements-build.txt

Write-Host "[3/4] 打包 ..."
pyinstaller --clean --noconfirm gateway\s7gateway.spec

Write-Host "[4/4] 复制可编辑的点表到 exe 旁边 ..."
Copy-Item -Force gateway\points.json dist\points.json
Copy-Item -Force gateway\README.md dist\README-gateway.md

Write-Host ""
Write-Host "打包完成: dist\s7gateway.exe"
Write-Host "自测（模拟 PLC,无需真机）:"
& dist\s7gateway.exe --mock --read-all
Write-Host ""
Write-Host "自测通过。接真机前先跑 dist\s7gateway.exe --browse 核对符号名。"
