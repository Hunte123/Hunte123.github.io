---
title: "纯 Go 从零实现 GPT：手推反向传播的完整记录"
date: 2026-10-23 15:40:00 +0800
categories: [技术教程]
tags: [Go, Transformer, 深度学习]
permalink: /posts/minigpt-go/
render_with_liquid: false
---

> 不用 PyTorch、不用任何自动微分框架——用纯 Go 写一个能训练的字符级 GPT，注意力的反向梯度自己推。仓库：[minigpt-go](https://github.com/Hunte123/minigpt-go)。

## 为什么自讨苦吃

用 PyTorch 写 Transformer，`loss.backward()` 一行搞定——但你也永远失去了理解它的机会。**手推反向传播是穿透框架黑盒的唯一路径**：softmax 的 Jacobian、注意力里 QKV 的梯度链、LayerNorm 里均值方差的回传——推过一遍，Transformer 对你就再无秘密。

## 三个最难啃的推导

**① softmax 反向**：`dx = y∘(dy - rowsum(dy∘y))`——一行公式，推的时候要想明白"概率归一化让梯度互相耦合"。

**② 注意力反向**（最硬核）：输出 `Out = att·v`，反向要同时回传四路——`dV = attᵀ·dOut`、`dAtt = dOut·vᵀ`、再过 softmax 反向拿到 `dScores`、最后 `dQ = dScores·k/√d` 且 `dK = dScoresᵀ·q/√d`（转置和缩放的位置极易搞错）。

**③ LayerNorm 反向**：归一化的均值和方差都是输入的函数，梯度要经过它们俩再回到输入——`dx = γ∘(dy - mean(dy) - x̂∘mean(dy∘x̂))/σ`，按行独立计算。

## 正确性怎么证明：数值梯度检查

手推的梯度凭什么信？**中心差分**：扰动每个参数 ±ε，数值算损失变化率，与解析梯度对比。`go test ./internal/nn/` 对 Linear/LayerNorm/Embedding/Attention 逐层检查，误差 < 1e-4 全部通过——这是全仓库最值钱的测试。

## 训练效果

字符级建模《红楼梦》第一回（351字词表）：

```
损失: 5.87 → 1.87（2500步，91秒，笔记本CPU）
```

损失降到 1.9 意味着模型已学会常用字搭配、标点节奏和文言句式残片；继续加大步数和模型规模，生成质量持续提升。重要的是：**这条训练曲线是纯 Go 代码跑出来的**——每一行梯度都是手写的。

## 工程取舍

- float64 而非 float32：梯度检查需要双精度
- 逐头循环而非 reshape：多头注意力直读透明
- 朴素 `[][]float64`：无优化——**看懂优先于跑快**

## 结语

框架是生产力，但从零实现是理解力。这个仓库和 Karpathy 的 llama2.c 属于同一精神谱系：**把魔法还原为数学**。推完这些梯度再看 PyTorch 的 autograd，你会对它心存敬意——也对它的每一步了如指掌。

仓库：[github.com/Hunte123/minigpt-go](https://github.com/Hunte123/minigpt-go)（MIT，含全部梯度检查测试）
