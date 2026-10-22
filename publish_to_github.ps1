# publish_to_github.ps1
# 作用：自动创建 GitHub 公开仓库 zy-3d-pipeline，并把本仓库推送上去。
# 用法：在文件资源管理器里对本文件点右键 -> "使用 PowerShell 运行"
# 前提：已完成一次 GitHub 登录授权（git credential helper = manager）
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$RepoName = "zy-3d-pipeline"
$Owner    = "theshy0j"

function Step($msg) { Write-Host "" ; Write-Host "== $msg ==" -ForegroundColor Cyan }

Step "1/4 读取本机 GitHub 凭据"
$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
if (-not $cred) {
    Write-Host "未取到凭据。请在本机 PowerShell 执行一次：" -ForegroundColor Red
    Write-Host "  git config --global credential.helper manager"
    Write-Host "  git ls-remote https://github.com/$Owner/$RepoName.git"
    Write-Host "并按弹出的窗口完成登录授权，然后重跑本脚本。"
    Read-Host "按回车退出"; exit 1
}
$token = ($cred | Select-String '^password=').Line -replace '^password=', ''
if (-not $token) { Write-Host "凭据里没有 token 字段，请重新登录授权后重试。" -ForegroundColor Red; Read-Host "按回车退出"; exit 1 }
Write-Host "  凭据已就绪" -ForegroundColor Green

Step "2/4 创建 GitHub 公共仓库 $Owner/$RepoName"
$headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json" }
$body = @{
    name        = $RepoName
    private     = $false
    description = "本地 3D 资产生成管线：照片/白模 -> TripoSR(MIT) -> Blender 清理/UV/法线 -> 3ds Max/V-Ray 精修。AI 出资产，人做精修。"
} | ConvertTo-Json
try {
    $repo = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body -ContentType "application/json"
    Write-Host ("  已创建：{0}  公开={1}" -f $repo.full_name, (-not $repo.private)) -ForegroundColor Green
    Write-Host ("  地址：{0}" -f $repo.html_url)
} catch {
    $msg = $_.Exception.Message
    if ($msg -match "already exists|422") {
        Write-Host "  仓库已存在，跳过创建（下面直接推送）" -ForegroundColor Yellow
    } else {
        Write-Host "  创建失败：$msg" -ForegroundColor Red
        Write-Host "  若是网络不通：本机 PowerShell 先设代理环境变量（HTTPS_PROXY）再重跑。"
        Read-Host "按回车退出"; exit 1
    }
}

Step "3/4 绑定远程仓库"
if ((git remote 2>$null) -contains "origin") {
    git remote set-url origin "https://github.com/$Owner/$RepoName.git"
    Write-Host "  origin 已更新 -> https://github.com/$Owner/$RepoName.git" -ForegroundColor Green
} else {
    git remote add origin "https://github.com/$Owner/$RepoName.git"
    Write-Host "  origin -> https://github.com/$Owner/$RepoName.git" -ForegroundColor Green
}

Step "4/4 推送（36.4MB，视网速 1-5 分钟）"
git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""; Write-Host "推送失败（原因见上方 git 报错）。常见原因：网络/代理不通，或远端仓库未创建。" -ForegroundColor Red
} else {
    Write-Host ""; Write-Host "推送完成！打开 https://github.com/$Owner/$RepoName 查看。" -ForegroundColor Green
}

Read-Host "按回车关闭窗口"
