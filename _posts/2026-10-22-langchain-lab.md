---
title: "LangChain 上手八课：从基础对话到 Agent 的渐进式练习"
date: 2026-10-22 22:40:00 +0800
categories: [技术教程]
tags: [LangChain, Python, AI]
permalink: /posts/langchain-lab/
render_with_liquid: false
---

> 8 个渐进式案例，从"第一次调用"走到"Agent与评估"，每个都是可运行的脚本。代码在 [langchain-lab](https://github.com/Hunte123/langchain-lab)。这是"框架+自研双修"路线的框架篇。

## 为什么用渐进式案例学框架

框架文档像字典——全但不成路径。这套练习的设计是**每课一个核心概念，后一课建立在前一课之上**，读完 8 个脚本，LangChain 的核心抽象就都有体感了：

| # | 案例 | 核心概念 |
|---|------|---------|
| 01 | chat_basic | invoke / stream / batch 三种调用 |
| 02 | prompts | 变量模板、角色消息、few-shot |
| 03 | lcel_chains | LCEL：`\|` 管道、RunnableParallel、RunnablePassthrough |
| 04 | structured_output | Pydantic + with_structured_output |
| 05 | rag | 切块/向量库/检索器/RAG链（零成本可跑） |
| 06 | agent | @tool + tool-calling Agent（真实行情工具） |
| 07 | memory | RunnableWithMessageHistory、会话隔离 |
| 08 | eval | batch + 断言式检查 |

## 三个值得说的设计点

**① LCEL 是框架的灵魂（案例03）。** `模板 | 模型 | 解析器` 的管道组合贯穿一切——RAG链、Agent、评估链全是同一套语法。学 LangChain 其实就是学"一切皆 Runnable"的思维方式。

**② 结构化输出是分水岭（案例04）。** `with_structured_output(Pydantic模型)` 让模型输出从"一段话"变成"可编程的对象"——字段描述就是给模型的输出说明书。到这一步，LLM 才真正接进业务代码。

**③ Agent = 模型 + 工具 + 循环（案例06）。** `@tool` 装饰器注册工具（docstring 即说明书），模型自主决定何时调用。案例里接的是真实的新浪行情接口——不是玩具 demo，是真能查到茅台股价的。

## 踩坑实录

**① 国内 pip 装不上。** PyPI 直连的索引响应被截断（JSON 解析错误）。解法一行：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（清华镜像）。

**② 脚本目录导入。** 每个案例是子目录里的独立脚本，`from common import init_llm` 会因 sys.path 不含仓库根而失败。统一在脚本头加两行路径引导，从任何目录都能跑。

**③ 模型服务的免费边界。** GLM 聊天模型（flash）免费，但 embedding 模型要付费——所以 05_rag 用确定性假向量保证零成本跑通，注释里标注了切换真实向量的那一行。

## 框架 vs 自研

这是本系列第三次回答同一个问题。现在两边都有作品了：

- **框架路线**（本仓库）：快速、标准、生态兼容——适合交付业务
- **自研路线**（[go-agent-lab](https://github.com/Hunte123/go-agent-lab) / [go-rag-memory-lab](https://github.com/Hunte123/go-rag-memory-lab)）：透明、可控、可定制——适合理解原理

**结论不是二选一，是先自研后框架**：手写过内核再用框架，每个抽象都知道它替你干了什么；出问题时能穿透黑盒。这套练习存在的意义，就是把"用过"变成"用过且知道底层是什么"。

仓库：[github.com/Hunte123/langchain-lab](https://github.com/Hunte123/langchain-lab)（MIT，所有案例配中文注释，任意 OpenAI 兼容服务可跑）
