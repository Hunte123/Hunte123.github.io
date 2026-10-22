---
title: "RAG 与 Agent Memory：用 Go 从零实现检索增强与跨会话记忆"
date: 2026-10-22 15:00:00 +0800
categories: [技术教程]
tags: [RAG, Memory, Go, AI]
permalink: /posts/go-rag-memory-lab/
render_with_liquid: false
---

> 一个真实项目的构建记录：RAG、Agent Memory、检索评测三件东西，用 Go 从零写完并开源。代码在 [go-rag-memory-lab](https://github.com/Hunte123/go-rag-memory-lab)。

## 一句话讲透两个概念

**RAG**（Retrieval-Augmented Generation）：生成之前先检索——把相关资料塞进上下文，让模型"开卷考试"而不是"闭卷瞎编"。

**Memory**：Agent 的记忆系统——本质是**对经验的 RAG**。把过去的事实存起来向量化，用到时按当前话题检索注入。想通这一点，两个模块就是同一套思想的两种应用。

## RAG 管线：四步

```
Ingest: 文档 → 中文感知切块 → 向量化 → 向量库（JSON持久化）
Ask:    问题 → 向量化 → TopK余弦检索 → 上下文注入 → 生成（带引用）
```

两个值得说的设计：

**切块要中文感知。** 按段落优先、超长段落按 rune 滑窗切块并保留重叠——按字节切会把中文拦腰斩断。

**系统提示词是 RAG 的另一半。** 只做检索不约束模型，它照样编。我们的提示词只有一句话的核心：*只依据资料回答，资料里没有就说不知道*。

## Memory：双轨结构（v0.2）

与 ChatGPT 记忆同构的双轨设计——事实轨与历史轨并存：

```
短期记忆：  近期对话的环形缓冲（完整但有限）
长期·事实轨：LLM抽取的持久事实（压缩，高信噪比）
长期·历史轨：原始对话逐轮向量化（不压缩，细节零丢失）
回忆：      按当前问题双轨检索 → 组装注入上下文
```

双轨的取舍是这篇博客最想说的设计观点：**事实轨检索出的都是干货但抽取有损；历史轨能召回当时原话但噪音更高**。只存事实，抽取时丢掉的语境永久丢失；只存原文，检索信噪比崩塌。主流产品（ChatGPT）选择了双轨并行，我们也是。

跨会话演示是这块的试金石——会话一陈述"持有葵花药业17600股、止损纪律是跌破支撑位就走"，抽取入库落盘；**会话二以全新进程启动**，仅凭检索出的记忆准确回答。实测：

```
用户: 我的止损纪律是什么？我当时原话是怎么说的？
助理: 您的止损纪律是跌破支撑位就走，绝不含糊。
      您当时的原话是："记住：我风险偏好中等，
      止损纪律是跌破支撑位就走，绝不含糊。"
（事实轨答干货，历史轨还原原话——双轨各自命中）
```

注意第二个答案：**模型引用的是当时说话的原文**——这个细节只存在于历史轨，任何事实抽取都会把它压扁。这就是双轨存在的理由。

## 评测先行：hit@k

标注集是"问题 → 应命中的文档"，统计 TopK 命中率。**RAG 的下限由检索决定**——检索不命中，生成再好也无用。示例集上内置检索器拿到 hit@1 = 100%，这才是敢接生成的底气。

## 实战踩坑实录

**① 向量模型的钱。** 聊天模型有免费档（GLM flash），但 embedding 模型要付费额度——冒烟测试当场翻车（"余额不足"）。解法反而成了项目亮点：**内置一个零依赖的本地哈希向量化器**（中文 2-gram + L2归一化），`RAG_EMBED_MODEL=local` 即启用，整个项目不配任何 Key 也能完整跑通。关键词级检索 ≈ BM25 风格，示例评测照样满分；要语义质量再切真实向量模型。

**② Go 的字段与方法不能同名。** 结构体字段 `Dim` 和接口方法 `Dim()` 撞名，编译器报错的角度很迷惑（"mismatched types func() int and untyped int"）。改名 `DimSize` 了事。

**③ `os.WriteFile` 不建父目录。** 第一次落盘向量库直接报 no such file。修复顺带成了开源质量细节：Save 自动 `MkdirAll`。

**④ 网络墙。** GitHub 推送三次断连（代理 reset、直连 hang up），最后加代理重试成功。国内做开源，推送要有重试的肌肉记忆。

## 用法

```bash
go build -o recall ./cmd/recall
export RAG_EMBED_MODEL=local          # 零Key模式；语义模式换真实向量模型
export RAG_BASE_URL=... RAG_API_KEY=... RAG_CHAT_MODEL=...

recall ingest --dir examples/docs     # 入库
recall ask "葵花药业的主打产品"        # 带引用问答
recall eval --set examples/evalset/set.json
recall memory-demo                     # 跨会话记忆演示
```

## 结语

RAG 不神秘，是"开卷考试"的工程化；Memory 不神秘，是对经验的检索；评测不神秘，是先证明检索再谈生成的纪律。这个项目连同上一个 [go-agent-lab](/posts/go-agent-lab/)（Agent 内核/编排/评测），把 Agent 技术栈的三块地基都从零写了一遍——**每个概念都亲手实现过，才算真正掌握。**

仓库：[github.com/Hunte123/go-rag-memory-lab](https://github.com/Hunte123/go-rag-memory-lab)（MIT，含单测与示例）
