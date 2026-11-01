---
title: Mac mini 上搭建 ComfyUI 跑 Wan 视频模型：从环境到出片完整实录
date: 2026-11-02 00:25:00 +0800
categories: [视频工程]
tags: [ComfyUI, Wan, 视频生成, Mac]
render_with_liquid: false
---

想在自己电脑上跑开源视频模型，门槛其实不高——前提是选对模型、避开几个坑。这篇是我在 Mac mini M4（16GB 内存）上从零搭建 ComfyUI、部署 Wan 2.2 视频模型、到实测出片的完整记录，包含每个坑的解法。

## ComfyUI 是什么

一句话：**节点式的视觉生成工作台**。界面是一张画布，上面摆一个个「节点」（方块），每个节点是一道工序（加载模型 / 编码文字 / 采样 / 解码 / 保存），节点之间连线，数据顺着连线流动，点「Queue」就开始跑整条流水线。

它好比视频界的 Blender：上手要理解节点思维，但一旦理解，任何模型（Wan、Hunyuan、FLUX、MiniMax H3……）都是「换一个 Loader 节点里的文件」的事。

## 第一步：干净的环境（标准安装）

不装整合包，全部官方源：

```bash
# 独立目录 + 独立venv，不污染系统
mkdir ~/comfyui-h3 && cd ~/comfyui-h3
python3.11 -m venv venv

# 官方仓库（国内网络挂代理：export https_proxy=http://127.0.0.1:7890）
git clone https://github.com/comfyanonymous/ComfyUI.git

# PyTorch 官方渠道（Mac自动启用MPS加速）
./venv/bin/pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cpu

# 依赖（国内强烈建议清华镜像）
./venv/bin/pip install -r ComfyUI/requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

启动：

```bash
cd ~/comfyui-h3/ComfyUI
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 ../venv/bin/python main.py \
  --port 18188 --listen 0.0.0.0
```

两个 Mac 专属要点：

- `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`：关掉 GPU 内存高水位限制，否则 16GB 机器加载稍大的模型就直接崩
- `--listen 0.0.0.0`：默认只监听本机，加这个参数后同一 WiFi 的手机、电脑都能用浏览器访问 `http://<Mac的IP>:18188`

## 第二步：选模型——16GB 内存的残酷数学

先算账再下载。跑视频模型需要三件套：**扩散模型（生成核心）+ 文本编码器（理解提示词）+ VAE（视频解码）**，三样都要装进内存。

我本来想跑 MiniMax H3，查完权重体积直接死心：

```text
H3 量化到最小：扩散模型 ~15GB + 编码器(Qwen3-VL-32B) ~14.6GB + VAE 2.6GB
→ 32GB+，16GB 怎么量化都塞不下
```

**Apple Silicon 是统一内存**：CPU 和 GPU 共用那 16GB，没有独立显存可以借——「显存不够拿内存顶」是 PC 独显的概念，Mac 上不成立。

最终选择 **Wan 2.2 TI2V-5B**（阿里开源，支持文生视频 + 图生视频，中文提示词友好），全部用 Q4_K_M 量化版：

| 组件 | 文件 | 体积 | 来源 |
| --- | --- | --- | --- |
| 扩散模型 | Wan2.2-TI2V-5B-Q4_K_M.gguf | 3.2GB | QuantStack/Wan2.2-TI2V-5B-GGUF |
| 文本编码器 | umt5-xxl-encoder-Q4_K_M.gguf | 3.4GB | city96/umt5-xxl-encoder-gguf |
| VAE | Wan2.2_VAE.safetensors | 1.3GB | QuantStack 同仓库 VAE 目录 |

三件套合计 7.9GB，加上系统和运行时，16GB 正好装下。

GGUF 量化版还需要一个插件才能加载：

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/city96/ComfyUI-GGUF.git
../venv/bin/pip install gguf -i https://pypi.tuna.tsinghua.edu.cn/simple
```

模型文件放到对应目录：`models/diffusion_models/`、`models/text_encoders/`、`models/vae/`。

**下载的坑**：HuggingFace 大文件走代理容易被重置，一定用 `curl -L -C -`（断点续传），并按字节数校验完整性（从 HF API 的 `x-linked-size` 响应头拿期望值）。我下载时被重置了两次，续传补齐即可。

## 第三步：ComfyUI 使用入门

打开浏览器进入界面后，核心概念只有三个：

1. **节点**：画布上的方块，每块是一道工序。视频工作流的最小骨架是：`UNETLoader → CLIPLoader → 文本编码 → 空Latent → KSampler → VAEDecode → 保存`
2. **连线**：节点上的圆点，连对了数据才能流动。用 GGUF 模型时注意 Loader 是 `UnetLoaderGGUF` / `CLIPLoaderGGUF`（插件提供的专用节点）
3. **Queue**：右上角提交按钮，点了才开始跑

几个必知操作：

- **看已装的模型**：点任意 Loader 节点中间的下拉框，列表就是该目录下所有可用文件
- **模板库**：左侧「工作流」图标 → Templates 标签，官方预置了几百个模型的工作流模板（Wan、H3、Hunyuan……），双击即载入画布。注意：模板 ≠ 已安装，载入后对应模型节点会标红提示缺权重
- **分辨率与步数**：KSampler 节点的 `steps` 和空 Latent 节点的宽高，直接决定显存占用和耗时
- **中文界面**：设置里可切换语言

## 实测：值不值得跑

Wan 2.2 5B Q4，832×480、20 步、5 秒 81 帧：

```text
推理 85.5秒/步 × 20 = 28分43秒
+ 文本编码 + VAE解码 ≈ 总计 35.6 分钟/段
内存全程稳定（顺序加载，不叠加占用）
```

结论很直白：**本地能出片，但慢**。它的定位不是日常生产，而是：

- 零成本验证想法、调试工作流
- 夜间挂机批量跑（睡一晚出十几段）
- 真要生产：API（1-2 分钟/段）或云 GPU（4090 约 5-15 分钟/段，每小时 2 块钱）

## 总结

```text
环境：官方 git clone + venv + 清华镜像，拒绝整合包
选型：先算内存账（三件套体积 + 系统占用 < 物理内存）
量化：GGUF Q4 + ComfyUI-GGUF 插件，小内存的唯一解
下载：curl -C - 断点续传 + 字节校验
使用：模板库找 workflow → Loader 下拉框选模型 → Queue
```

搭建本身不到一小时，真正花时间的是选型算账和下载重试。这套流程对任何开源视频模型通用——换模型就是换三件套文件，环境骨架一模一样。
