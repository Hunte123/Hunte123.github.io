---
title: "从零写一个 Go Agent 框架：内核、编排、评测三件套"
date: 2026-10-22 13:00:00 +0800
categories: [技术教程]
tags: [Go, AI, Agent, MCP]
permalink: /posts/go-agent-lab/
render_with_liquid: false
---

> 本文是一个真实项目的构建记录：一天之内，从"Agent 是什么"到开源一个可跑通的三合一框架。代码在 [go-agent-lab](https://github.com/Hunte123/go-agent-lab)。

## 三件套是什么

一个自包含的 Go 项目，三层递进：

1. **Agent 内核**——不依赖任何框架，核心循环百行实现
2. **多 Agent 编排**——数据员→分析师→撰稿人，输入股票代码、输出 Markdown 研报
3. **评测框架**——JSON 定义任务、终态验收、多轮统计

## 内核：Agent 就是一个循环

剥掉所有魔法，Agent 的本质是这个：

```go
for step := 1; step <= maxSteps; step++ {
    reply := llm.Complete(ctx, messages, tools)  // 思考
    if len(reply.ToolCalls) == 0 {
        return reply.Content                     // 最终答案
    }
    messages = append(messages, reply)
    for _, call := range reply.ToolCalls {
        out := tools.Execute(call)                // 行动
        messages = append(messages, toolResult(out)) // 观察
    }
}
```

**思考 → 行动 → 观察**，循环到模型不再要工具为止。工具就是带 JSON Schema 声明的普通函数，`docstring` 写给模型看，参数按 Schema 校验执行。

## 编排：三个角色显式交接

```
数据员（行情工具）→ 分析师（纯推理）→ 撰稿人（纯输出）
      拿数              分析            成稿
```

每一棒的 Answer 是下一棒的任务输入。角色刻意做了职权分离：数据员禁止分析、分析师禁止编造数据、撰稿人不碰工具。跑一次真实流水线（GLM-4.5-Flash）：

```
数据员[2步/2次工具/9s] → 分析师[1步/16s] → 撰稿人[1步/38s] ✅ 研报落盘
```

## 评测：只验收终态

任务是一段 JSON：给 Agent 的指令 + 若干验收器。

```json
{
  "name": "quote_fetch",
  "prompt": "查询贵州茅台(600519)行情，写入 price.txt……",
  "verifiers": [
    {"type": "file_exists", "path": "price.txt"},
    {"type": "file_contains", "path": "price.txt", "regex": "茅台"}
  ]
}
```

三条铁律：**验收只看终态不看过程；验收器在 Agent 够不到的层面执行；每题多次运行取统计**。输出通过率、平均 token、平均耗时——Agent 的好坏从此有数可依。

## 冒烟测试抓出的两个真 Bug

比代码更值钱的部分：

**① 沙箱路径穿越。** 文件工具本该把 Agent 钉死在工作目录内，但单元测试发现 `../evil.txt` 成功写出去了——路径清洗逻辑形同虚设。修复：含 `..` 直接拒绝，不搞默默清洗。**教训：安全代码必须有对应的失败测试。**

**② 长文本经工具参数传递易碎。** 撰稿人 Agent 连续两轮死循环（12 步全是工具调用，2.8 万 token 打水漂）。表面是"模型不听话"，根因是：让模型把几千字 Markdown 塞进工具调用的 JSON 字符串参数里，转义一碎就写入失败，失败就重试，重试再失败。修复是架构级的：**Agent 只负责思考输出文本，文件 I/O 归编排层代码**。一轮修好后撰稿人从 12 步死循环变成 1 步直达。

**教训：不要让大载荷穿过工具调用的 JSON 通道。Agent 的职责是推理，环境操作归宿主代码。**

## 用法

```bash
go build -o agentlab ./cmd/agentlab
export AGENTLAB_BASE_URL=...  # 任意 OpenAI 兼容服务
export AGENTLAB_API_KEY=...
export AGENTLAB_MODEL=...

./agentlab study --codes 600519,002737   # 研报流水线
./agentlab eval --tasks examples/tasks   # 评测跑批
```

模型完全可换：OpenAI / GLM / DeepSeek / 本地 Ollama，协议一致即插即用。

## 结语

Agent 不神秘，它是一个带工具的 while 循环；多 Agent 不神秘，是显式交接的流水线；评测不神秘，是只认终态的自动化验收。真正的工程量在三件事上：**沙箱安全、失败模式、载荷设计**——这三件，恰好都是冒烟测试替我们发现的。

仓库：[github.com/Hunte123/go-agent-lab](https://github.com/Hunte123/go-agent-lab)（MIT，含单元测试与示例任务）
