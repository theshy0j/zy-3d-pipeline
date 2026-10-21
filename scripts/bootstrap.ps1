# bootstrap.ps1 — 新机器一键搭环境（Windows / PowerShell 5.1）
# 用法：在仓库根目录右键“使用 PowerShell 运行”，或：
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
#
# 可选环境变量：
#   PIP_INDEX      PyPI 镜像源（默认阿里云，国内快；海外用户设 https://pypi.org/simple）
#   TORCH_CUDA     torch 的 CUDA 版本代号（默认 cu126，需驱动 >= 525；更老的驱动用 cu121/cu118）
#   BLENDER_BIN    blender.exe 路径（默认找 PATH）
#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# 项目根目录 = 本脚本所在目录（scripts\）的上一级
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
$Index = if ($env:PIP_INDEX) { $env:PIP_INDEX } else { "https://mirrors.aliyun.com/pypi/simple/" }
$TorchCu = if ($env:TORCH_CUDA) { $env:TORCH_CUDA } else { "cu126" }

Write-Host "== 1/6 创建 venv（有 uv 用 uv，没有就用系统 python）=="
if (Test-Path $Py) {
    Write-Host "  .venv 已存在，跳过创建"
} elseif (Test-Path $Uv) {
    & $Uv venv --python 3.12 --seed .venv
} else {
    python -m venv .venv
}

Write-Host "== 2/6 安装 torch（CUDA 版，约 2.7GB，从 download.pytorch.org）=="
# ⚠️ 必须先装 CUDA 版 torch：PyPI/镜像源上的 Windows torch 是 CPU 构建，
#    先装它再装 requirements.txt 会被误判“已满足”而跳过，GPU 直接不可用。
& $Py -m pip install --no-cache-dir --retries 5 --timeout 120 --index-url "https://download.pytorch.org/whl/$TorchCu" torch torchvision
if ($LASTEXITCODE -ne 0) { throw "torch 安装失败（CUDA=$TorchCu）。驱动太老可换 TORCH_CUDA=cu121 重试" }

Write-Host "== 3/6 安装其余 Python 依赖（源：$Index）=="
& $Py -m pip install --no-cache-dir --retries 5 --timeout 120 -i $Index -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

Write-Host "== 4/6 安装 torchmcubes CPU shim（无 MSVC 环境的 marching cubes）=="
& $Py -m pip install --no-cache-dir -i $Index "./third_party/torchmcubes-cpu-shim"
if ($LASTEXITCODE -ne 0) { throw "shim 安装失败" }

Write-Host "== 5/6 获取 TripoSR 源码 + 打 Windows 补丁 =="
if (-not (Test-Path "third_party\TripoSR\run.py")) {
    New-Item -ItemType Directory -Force -Path third_party | Out-Null
    $tar = Join-Path $env:TEMP "triposr-main.tar.gz"
    # 如 codeload 太慢，可把下面 URL 换成 ghproxy 镜像，例如：
    #   https://ghproxy.net/https://github.com/VAST-AI-Research/TripoSR/archive/refs/heads/main.tar.gz
    & curl.exe -L --fail --retry 3 --max-time 900 -o $tar "https://codeload.github.com/VAST-AI-Research/TripoSR/tar.gz/refs/heads/main"
    & tar -xzf $tar -C third_party
    New-Item -ItemType Directory -Force -Path "third_party\TripoSR" | Out-Null
    Move-Item -Force "third_party\TripoSR-main\*" "third_party\TripoSR\"
    if (Test-Path "third_party\TripoSR-main\.gitattributes") {
        Move-Item -Force "third_party\TripoSR-main\.gitattributes" "third_party\TripoSR\"
    }
    Remove-Item -Recurse -Force "third_party\TripoSR-main"
} else {
    Write-Host "  third_party\TripoSR 已存在，跳过"
}
& $Py scripts\patch_triposr.py
if ($LASTEXITCODE -ne 0) { throw "补丁失败" }

Write-Host "== 6/6 环境自检 =="
& $Py tests\verify_setup.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "自检未通过，请把上面的输出发给维护者"
    exit 1
}
Write-Host ""
Write-Host "bootstrap 完成。下一步："
Write-Host "  1) python scripts\download_models.py        # 下载模型权重（约 1.6GB + DINO 330MB）"
Write-Host "  2) powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1"
