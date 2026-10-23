---
title: "dramapipe：把小说变成短剧的自动化流水线"
date: 2026-10-23 11:50:00 +0800
categories: [技术教程]
tags: [AI, 短剧, Python, Pipeline]
permalink: /posts/dramapipe/
render_with_liquid: false
---

> 从"手动做一集短剧烧掉一整天"到"一条命令跑五个阶段"——[dramapipe](https://github.com/Hunte123/dramapipe) 把踩坑经验固化成了流水线。

## 做过一集短剧，才知道坑在哪

真刀真枪做完一集AI短剧（60秒竖屏、图生视频、配音混音全流程）后，最深的体会是：**每一步都可能失败，失败后要能只重跑那一步**。裁到倾家荡产的额度教会我们的架构：

```
novel.md → [script] → 制作包 → [frames] → [video] → [audio] → [assemble] → final.mp4
```

五个阶段，互相只通过磁盘产物通信，`manifest.json` 记录状态——**任何阶段可独立重跑，视频阶段自带断点续跑**（最贵的阶段最需要）。

## 精简是刻意的

v0.1 只有核心骨架：状态机 + 供应层 + 五个阶段函数。角色一致性、字幕动效、BGM混音、自动QC都在路线图里等着，但**没有塞进第一版**——先把地基打对，扩展是加法不是重写。

零依赖（Python标准库+ffmpeg），LLM走OpenAI兼容协议任意换，图/视频/语音是MiniMax实战验证过的调用模式。

## 最便宜的一步免费

只配一个免费的GLM key，`run script` 就能把小说变成完整制作包（分镜表+逐镜Prompt+台词表）——实测一段300字小说，LLM产出11镜完整分镜，结构齐全直接可用。后续烧钱的阶段（生图/生视频）配了key再跑。

## 一分钟体验

```bash
git clone https://github.com/Hunte123/dramapipe && cd dramapipe
export DRAMA_LLM_API_KEY=***
cp -r examples/demo-drama /tmp/drama && cd /tmp
python -m dramapipe new drama && cp demo-drama/novel.md demo-drama/config.json drama/
python -m dramapipe run script drama
```

仓库：[github.com/Hunte123/dramapipe](https://github.com/Hunte123/dramapipe)（MIT）
