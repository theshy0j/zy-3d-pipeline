# USAGE.md —— 小白上手指南

> 这份指南回答三个问题：**怎么用？还要干什么？出问题找谁？**
> 工程细节（补丁原理、授权条款）在 [README.md](README.md)，这里只讲日常操作。

---

## 0. 一句话说明这是什么

把你的一张照片/白模图，变成一个**能拖进 3ds Max 继续精修的 3D 模型**（FBX）。
AI 负责出「毛坯资产」，你（或你的 DCC 软件）负责精修。它不是端到端自动生成。

```
你的图 ──▶ AI 重建（约 1 分钟）──▶ Blender 自动清理（约 1 分钟）──▶ clean.fbx / clean.glb
```

---

## 1. 第一次使用（只做一次）

在仓库根目录（`zy-3d-pipeline\`）打开 PowerShell，跑：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

它会自动装好全部环境（Python 依赖、CUDA 版 torch、下载 TripoSR 源码打补丁），
约 15–30 分钟（取决于网速，主要耗时是下载 2.7GB 的 torch）。
跑完后它会提示你下载模型权重（约 1.6GB），照提示做即可。

> 环境只装一次。以后每次用**直接从第 2 节开始**。

---

## 2. 日常使用（三步）

### 第 1 步：放图

新建一个文件夹放你的图，图片**必须命名为 `input.png`**：

```
samples\myasset\input.png     ← 你的照片/白模放这里
```

### 第 2 步：跑一条命令

```powershell
$env:SKIP_GEN_INPUTS = "1"
$env:CASES = "myasset"
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
```

等 2–5 分钟（一张图；AI 重建约 1 分钟 + Blender 清理约 1 分钟 + 渲染拼图约 1 分钟）。

### 第 3 步：拿产物

去 `samples\myasset\` 拿这些文件：

| 文件 | 是什么 | 给谁用 |
|---|---|---|
| **`clean.fbx`** | **主产物**：清理后的模型 | 拖进 3ds Max / V-Ray 精修 |
| **`clean.fbm\`** | FBX 的贴图目录 | **拷 FBX 时必须一起拷**，否则贴图丢失 |
| `clean.glb` | 同模型 GLB 版 | 引擎/预览器/直接发给别人看 |
| `before_after.png` | 输入 vs 重建对比图 | 判断这次重建值不值得精修 |
| `recon.json` / `clean.json` | 耗时/显存/网格数/水密性报告 | 排查用，平时不用管 |

> 其他文件（`raw.obj`、`texture.png`、`model_input.png`）是中间产物，不用管。

---

## 3. 常见问题（按出现频率排序）

**Q1：`clean.fbx` 拖进 3ds Max 没有贴图？**
贴图在旁边的 `clean.fbm\` 目录里（FBX 的 `path_mode=COPY` 模式）。
把 FBX 和 `clean.fbm\` 一起拷贝/压缩，别只拷 FBX 单文件。

**Q2：重建结果跟我的图不像怎么办？**
这是单图重建的固有限制（README §6「重建保真度」有详细说明）。
AI 产物定位是「可编辑毛坯」——形态修正本来就是 DCC 精修的活。
想让初始保真度高一点：换**有真实纹理的照片**（无纹理白模效果最差）。

**Q3：`clean.json` 里 `watertight: false` 是什么意思？**
模型有破洞（边界边）。`interior` 案例就有 3 条。
不影响拖进 3ds Max，但精修/3D 打印前需要在 DCC 里补洞。

**Q4：想同时跑多张图？**
`samples\` 下建多个案例目录，`CASES` 用逗号分隔：

```powershell
$env:CASES = "myasset,chair2,room3"
```

**Q5：跑之前想先确认环境没坏？**

```powershell
.venv\Scripts\python.exe tests\verify_setup.py
```

全过就没问题；哪项红了照提示修（一般是 Blender 不在 PATH 里，设 `BLENDER_BIN` 环境变量）。

**Q6：报错去哪看？**
每个案例目录里的 `recon.json` / `clean.json` 有当次运行数据；
PowerShell 窗口里的报错栈最后几行通常就是原因。
疑难杂症查 README §6「已知限制」和 §7「补丁说明」。

**Q7：内置三个案例（building/interior/furniture）是干嘛的？**
是随仓库的验证样本，证明管线在这台机器上跑通过。
你可以直接用同名目录覆盖它们来跑自己的图（不设 `CASES` 时默认跑这三个）。

---

## 4. 还需要干什么（收尾待办）

按优先级：

| # | 事项 | 状态 |
|---|---|---|
| 1 | **push 到 GitHub**：`git remote add origin <你的仓库地址>` + `git push -u origin main`，push 前先把占位身份改成你的（`git config user.email "<你的邮箱>"`） | ⬜ 待办 |
| 2 | **用真实照片做一轮对比实验**：同一样东西拍张照片跑一次，和白模结果比保真度（决定以后输入该用照片还是白模） | ⬜ 建议 |
| 3 | **3ds Max 末端实测**：本机没装 3ds Max/V-Ray，FBX 交换路径未经真实 DCC 验证；拿到你机器上拖一个 `clean.fbx` 确认材质/UV 正常 | ⬜ 建议 |
| 4 | 正式投产时把占位输入图换成你有权利的照片，并在 `LICENSE_LOG.md` §6 登记 | ⬜ 用时 |

---

## 5. 命令速查（复制即用）

```powershell
# 第一次：装环境（只做一次）
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

# 日常：跑自己的图
$env:SKIP_GEN_INPUTS = "1"; $env:CASES = "myasset"
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1

# 环境自检
.venv\Scripts\python.exe tests\verify_setup.py

# 高级：跳过 Blender 阶段，只要 AI 重建的原始网格
.venv\Scripts\python.exe scripts\run_recon.py --input samples\myasset\input.png --outdir samples\myasset --bake-texture
```

---

## 6. 分阶段手动跑（高级，平时用不到）

`run_all.ps1` 是七步串起来的流水线，每步都可以单独跑（调试某一阶段时用）：

| 阶段 | 命令 |
|---|---|
| 生成占位输入图 | `blender -b --python scripts\gen_inputs.py -- --out .` |
| 确认/下载权重 | `.venv\Scripts\python.exe scripts\download_models.py` |
| AI 重建 | `.venv\Scripts\python.exe scripts\run_recon.py --input samples\myasset\input.png --outdir samples\myasset --bake-texture` |
| Blender 清理 | `blender -b --python scripts\clean_mesh.py -- --input samples\myasset\raw.obj --texture samples\myasset\texture.png --outdir samples\myasset` |
| 渲染 After 图 | `blender -b --python scripts\render_before_after.py -- --input samples\myasset\clean.glb --outdir samples\myasset` |
| 拼对比图 | `.venv\Scripts\python.exe scripts\make_compare.py --before samples\myasset\input.png --after samples\myasset\after.png --out samples\myasset\before_after.png` |
