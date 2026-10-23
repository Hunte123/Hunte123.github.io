---
title: "开源一个跨 Agent 技能仓库：一处收集，处处安装"
date: 2026-10-23 11:30:00 +0800
categories: [技术教程]
tags: [AI, Agent, Skills]
permalink: /posts/agent-skills/
render_with_liquid: false
---

> SKILL.md 已成跨工具标准：Claude Code、Codex、OpenClaw 都认。那技能收集也该有一处统一的地方——[agent-skills](https://github.com/Hunte123/agent-skills)。

## 是什么

一个技能收集仓库：每个技能一个目录 + 标准 SKILL.md，配一个安装器自动检测本机装了哪些 Agent，一条命令装进去：

```bash
./install.sh list        # 看有什么
./install.sh <技能名>     # 装进检测到的所有agent
./install.sh all --copy  # 全装（复制模式）
```

默认软链安装——仓库 `git pull` 一次，所有 agent 的技能同步更新。

## 为什么

技能散落在各工具的私有目录里，换工具就要重收集一遍。按统一标准集中管理 + 一键分发，收集一次，处处可用。新工具适配只需在安装器的目录表加一行。

## 怎么贡献

复制 `example-skill` 模板，写好 SKILL.md（三条铁律：frontmatter 写清触发场景、正文是可执行步骤、自包含），提 PR 即可。规范三分钟读完：[CONTRIBUTING.md](https://github.com/Hunte123/agent-skills/blob/main/CONTRIBUTING.md)。

仓库：[github.com/Hunte123/agent-skills](https://github.com/Hunte123/agent-skills)（MIT）
