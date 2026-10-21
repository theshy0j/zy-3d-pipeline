# run_all.ps1 — 一键跑完整管线（三个案例：建筑 / 室内 / 家具）
# 前置：先跑 scripts\bootstrap.ps1
# 用法：powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
# 环境变量：
#   BLENDER_BIN   Blender 可执行文件路径（默认找 PATH 里的 blender）
#   SKIP_GEN_INPUTS=1   跳过占位输入图生成（已换成自己的照片时用）
#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# 项目根目录 = 本脚本所在目录（scripts\）的上一级
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location $Root

$Py = ".venv\Scripts\python.exe"
$Blender = $env:BLENDER_BIN
if (-not $Blender) { $Blender = "blender" }
$cases = @("building", "interior", "furniture")

# 国内机器访问 HuggingFace 需要镜像；海外机器删掉这两行
$env:HF_ENDPOINT = "https://hf-mirror.com"

# xatlas 装上了就走“烘焙贴图”路径（UV + texture.png），否则走顶点色路径
$bake = $false
& $Py -c "import xatlas" 2>$null
if ($LASTEXITCODE -eq 0) { $bake = $true }
$texPath = "vertex-color"
if ($bake) { $texPath = "bake-texture (xatlas)" }
Write-Host "texture path: $texPath"

if ($env:SKIP_GEN_INPUTS -ne "1") {
    Write-Host "== 1/7 生成占位输入图（占位素材，可换成你自己的照片）=="
    & $Blender -b --python scripts\gen_inputs.py -- --out $Root
} else {
    Write-Host "== 1/7 跳过输入图生成（SKIP_GEN_INPUTS=1）=="
}

Write-Host "== 2/7 确认模型权重 =="
& $Py scripts\download_models.py --verify > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -- 首次运行，下载权重（约 1.6GB）"
    & $Py scripts\download_models.py
    if ($LASTEXITCODE -ne 0) { throw "权重下载失败（见 scripts/download_models.py 输出）" }
} else {
    Write-Host "  -- 权重已缓存，跳过下载"
}

Write-Host "== 3/7 AI 重建（TripoSR）=="
foreach ($c in $cases) {
    Write-Host "  -- $c"
    if ($bake) {
        & $Py scripts\run_recon.py --input "samples\$c\input.png" --outdir "samples\$c" --bake-texture
    } else {
        & $Py scripts\run_recon.py --input "samples\$c\input.png" --outdir "samples\$c"
    }
    if ($LASTEXITCODE -ne 0) { throw "run_recon 失败: $c" }
}

Write-Host "== 4/7 Blender 清理 + 导出 FBX/GLB =="
foreach ($c in $cases) {
    Write-Host "  -- $c"
    if ($bake) {
        & $Blender -b --python scripts\clean_mesh.py -- --input "samples\$c\raw.obj" --texture "samples\$c\texture.png" --outdir "samples\$c"
    } else {
        & $Blender -b --python scripts\clean_mesh.py -- --input "samples\$c\raw.glb" --outdir "samples\$c"
    }
    if ($LASTEXITCODE -ne 0) { throw "clean_mesh 失败: $c" }
}

Write-Host "== 5/7 渲染 After 图 =="
foreach ($c in $cases) {
    Write-Host "  -- $c"
    & $Blender -b --python scripts\render_before_after.py -- --input "samples\$c\clean.glb" --outdir "samples\$c"
    if ($LASTEXITCODE -ne 0) { throw "render 失败: $c" }
}

Write-Host "== 6/7 拼 Before/After 对比图 =="
foreach ($c in $cases) {
    & $Py scripts\make_compare.py --before "samples\$c\input.png" --after "samples\$c\after.png" --out "samples\$c\before_after.png"
    if ($LASTEXITCODE -ne 0) { throw "make_compare 失败: $c" }
}

Write-Host "== 7/7 汇总 =="
foreach ($c in $cases) {
    $d = "samples\$c"
    $mark = "MISSING"
    if (Test-Path "$d\before_after.png") { $mark = "OK" }
    Write-Host "  $c : $mark"
}
Write-Host ""
Write-Host "完成。每个案例目录：input.png / before_after.png / clean.glb / clean.fbx / recon.json / clean.json"
