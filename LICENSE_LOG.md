# 授权台账 LICENSE_LOG.md

> 本文件登记 zy-3d-pipeline 管线中用到的**每一个第三方模型与工具**的授权状态。
> 规则：结论必须附来源链接；无法核实的必须写「未核实」，不许凭记忆写。
> 最近核查日期：**2026-10-21**（新增/替换引擎时必须同步更新本文件）。

## 总览

| 组件 | 授权 | 免费商用处境 | 门槛/限制 | 本管线角色 | 默认启用 |
|---|---|---|---|---|---|
| TripoSR（代码+权重） | MIT | 可，无条件 | 保留 MIT 声明 | 图→网格主引擎 | ✅ |
| SF3D | Stability AI Community License | 年收入 ≤ $1M 可，超出需 Enterprise License | HF 权重 gated，需账号同意条款 | 可选升级引擎 | ❌ |
| Hunyuan3D-2.1 | Tencent Hunyuan 3D 2.1 Community License | 可，但地域排除 EU/英国/韩国 | MAU > 100 万需向腾讯单独申请 | 备选引擎（12GB 显存偏紧） | ❌ |
| Blender 4.5 LTS | GPL-2.0-or-later | — | 本仓库脚本为原创，经 bpy 调用 | 清理/UV/法线/渲染/导出 | ✅ |
| 3ds Max / V-Ray | 商业软件 | 授权由使用方自理 | FBX 交换 | DCC 精修（管线末端） | ✅（人工环节） |
| 本仓库代码 | MIT | 可 | 保留 MIT 声明 | — | ✅ |

## 1. TripoSR —— 默认引擎（已验证）

- **授权**：MIT（源代码与预训练权重均 MIT）。
- **代码仓库**：https://github.com/VAST-AI-Research/TripoSR （README 原文：*"The model is released under the MIT license, which includes the source code, pretrained models, and an interactive online demo."*）
- **权重**：https://huggingface.co/stabilityai/TripoSR （文件 `model.ckpt`，约 1.6GB）
  - 2026-10-21 经 HF API 核实：`"gated": false`、`"license": "mit"` —— **无门禁，可自动下载**，这是选它作默认引擎的决定性原因。
- **官方声明显存需求**：README 称默认参数单图约 6GB VRAM；本机 RTX 2060 12GB 实测峰值 **1.82GB**（256³ 默认参数），数据见 `samples/*/recon.json` 与 README §3.1 实测表。
- **义务**：再分发时保留 MIT 版权与许可声明（本仓库以 vendored 副本 + 本文件履行）。
- **其他来源**：https://stability.ai/news/triposr-3d-generation （Stability AI 与 Tripo AI 联合发布，MIT，允许商用）。

## 2. SF3D —— 可选升级（默认不使用）

- **授权**：Stability AI Community License。
- **条款要点**（来源：https://stability.ai/news/introducing-stable-fast-3d 与 https://stability.ai/license ）：
  - 年收入 ≤ 100 万美元的个人/机构：研究、非商业、商业使用**均免费**；
  - 年收入 > 100 万美元：须先获得 Stability AI Enterprise License 才能商用模型或其衍生品/输出。
- **权重仓库**：https://huggingface.co/stabilityai/stable-fast-3d —— **gated 仓库**（HF 模型卡含 `extra_gated_*` 字段），需注册 HF 账号、手动同意条款并提供 Token 才能下载。
- **默认不用的原因**：gated 依赖人工步骤，破坏「新机器按 README 一键复现」的验收标准；且其输出（UV+贴图）虽优于 TripoSR，但 TripoSR + Blender 清理足以覆盖本管线定位。
- **如需启用**：见 README「可选引擎」一节，自行接受条款后设置 `HF_TOKEN` 环境变量。

## 3. Hunyuan3D-2.1 —— 备选（未使用）

- **授权**：Tencent Hunyuan 3D 2.1 Community License Agreement（来源：https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE ）。
- **条款要点**：
  - 免授权费，非独占、不可转让；**地域 = 全球但排除欧盟、英国、韩国**（Territory 定义节）；
  - 上月 MAU > 100 万的产品/服务，须向腾讯（hunyuan3d@tencent.com）申请许可；
  - 分发第三方须附协议副本 + Notice 文件 + 标明「Powered by Tencent Hunyuan」；
  - **Outputs（生成的网格/纹理）不属于 Model Derivatives，归使用者所有**（LICENSE 定义节；另见 https://deepwiki.com/Tencent-Hunyuan/Hunyuan3D-2.1/8-licensing-and-usage 对 Outputs/Model Derivatives 的区分解读）。
- **未使用原因**：12GB 显存跑形状生成已接近上限；且地域排除条款对欧盟方向用户不友好。此处登记备选。

## 4. Blender 4.5.3 LTS

- 授权：GPL-2.0-or-later（https://www.blender.org/about/license/ ）。
- 本仓库 `scripts/*.py` 中在 Blender 内运行的脚本均为**原创**，通过 `bpy` API 驱动，不包含 Blender 源码。

## 5. 3ds Max / V-Ray（管线末端人工精修）

- Autodesk / Chaos 商业软件，授权由使用方自理；本管线交付 **FBX**（Blender → 3ds Max 的标准交换格式，随纹理拷贝）与 **GLB** 两种格式。

## 6. 示例输入图（samples/*/input.png）

- 由本仓库 `scripts/gen_inputs.py` 在 Blender 中程序化渲染生成，**不含任何第三方资产**，以 CC0（公有领域）提供。
- ⚠️ 它们是**占位素材**，仅用于验证链路与复现。正式投产时请替换为你拥有权利的照片/白模，并在此登记每张图的来源与授权。

## 7. Python 依赖

| 包 | 授权 | 说明 |
|---|---|---|
| torch / torchvision | BSD-style（PyTorch License） | CUDA 12.6 轮子 |
| transformers | Apache-2.0 | TripoSR 图像编码器 |
| trimesh | MIT | 网格读写 |
| xatlas | BSD-3-Clause | TripoSR `--bake-texture` 的 UV 展开（如启用） |
| rembg | MIT | 背景移除（可选，默认关闭） |
| onnxruntime | MIT | rembg 推理后端（可选） |

> 版本以 `requirements.txt` 锁定为准；新增依赖必须同步登记本表。
