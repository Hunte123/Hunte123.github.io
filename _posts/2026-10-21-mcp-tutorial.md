---
title: "MCP 实战：30分钟给你的 AI 接上工具"
date: 2026-10-21 12:30:00 +0800
categories: [技术教程]
tags: [MCP, AI, Python]
permalink: /posts/mcp-tutorial/
render_with_liquid: false
---

> 本文基于一次真实的开发记录：从一个疑问（"MCP 是啥"）到一个在生产环境服务微信查询的行情服务器，全程约 30 分钟。

## MCP 是什么

**Model Context Protocol**，Anthropic 开源的 AI 工具接入协议——**AI 界的 USB-C**。

在此之前，每个 AI 连每个工具都要单独开发；有了 MCP，工具方把能力封装成"MCP 服务器"，任何支持协议的 AI（Claude、ChatGPT 桌面版、Cursor、OpenClaw……）即插即用。一次开发，处处可用。

三个核心概念，一分钟讲完：

| 概念 | 是什么 | 类比 |
|------|--------|------|
| Tools | AI 可调用的函数 | 函数调用 |
| Resources | 只读数据源 | GET 请求 |
| Prompts | 预制提示模板 | 快捷指令 |

服务器分两种形态：**本地型**（stdio，客户端自动拉起、用完回收，用户无感）和**远程型**（HTTP 常驻服务，需自行保活）。个人使用选本地型，配置完就当它不存在。

## 实战：A股行情服务器

### 环境

需要 Python 3.10+（官方 SDK 硬要求，3.9 会装不上）：

```bash
python3.11 -m venv venv
venv/bin/pip install 'mcp<2'
```

### 完整代码（约 80 行）

```python
# server.py —— 三层架构：工具层 / 传输层 / 数据层
import re, os, json, subprocess, urllib.parse
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("astock")  # 服务器名，工具会带这个前缀

def _sina_get(url: str) -> str:
    """数据层：新浪接口只认 curl（urllib 会被降级返回全零），GBK 解码"""
    r = subprocess.run(["curl", "-s", "-m", "10",
        "-H", "Referer: https://finance.sina.com.cn", url],
        capture_output=True, timeout=15)
    return r.stdout.decode("gbk", "ignore")

def _full_code(code: str) -> str:
    """6 位代码自动加市场前缀：6 开头沪市，0/3 开头深市"""
    if re.fullmatch(r"\d{6}", code):
        return ("sh" if code.startswith("6") else "sz") + code
    return code

@mcp.tool()
def get_quote(code: str) -> str:
    """查询A股实时行情。code：sh600519 / 纯6位数字；指数如 sz399001"""
    code = _full_code(code.strip())
    raw = _sina_get(f"https://hq.sinajs.cn/list={code}")
    m = re.search(r'="([^"]+)"', raw)
    if not m or not m.group(1):
        return f"未查到 {code}"
    p = m.group(1).split(",")
    last, prev = float(p[3]), float(p[2])
    if last == 0:  # 盘前/停牌：最新价为 0，用昨收兜底
        return f"{p[0]}（{code}）【盘前/停牌】昨收 {prev:.2f}"
    pct = (last - prev) / prev * 100
    return f"{p[0]}（{code}）最新 {last:.2f}（{pct:+.2f}%）"

@mcp.tool()
def search_stock(keyword: str) -> str:
    """按中文名或代码搜A股，例：茅台 / 000001"""
    kw = keyword.strip()
    hits = [s for s in _STOCKS if kw in s["name"]] or \
           [s for s in _STOCKS if kw in s["code"]]
    return "\n".join(f"{s['name']}  {_full_code(s['code'])}" for s in hits[:8]) or "没搜到"

# 本地股票列表：离线搜索，零网络依赖
_LIST = os.path.expanduser("~/.openclaw/workspace/stock-picker/cache/stock_list.json")
_STOCKS = json.load(open(_LIST)) if os.path.exists(_LIST) else []

if __name__ == "__main__":
    mcp.run()  # stdio 模式：等待客户端的 JSON-RPC 调用
```

**设计要点**：每个工具就是普通 Python 函数——`@mcp.tool()` 一行注册，**docstring 就是 AI 的说明书**（AI 靠它判断何时用、参数怎么填），参数按 JSON Schema 校验传值，函数返回什么 AI 就看到什么。

### 协议级自测

不接客户端也能验证，写 20 行测试模拟完整调用链：

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="venv/bin/python", args=["server.py"])
    async with stdio_client(params) as (read, write):      # 拉起服务器
        async with ClientSession(read, write) as s:        # 建立会话
            await s.initialize()                           # 握手
            print([t.name for t in (await s.list_tools()).tools])
            r = await s.call_tool("get_quote", {"code": "600519"})
            print(r.content[0].text)

asyncio.run(main())
```

看到工具列表和行情输出，协议链路即通。

### 接入客户端

各客户端配置格式略有差异，本质相同——告诉它"用哪个命令启动这个服务器"：

- **OpenClaw**：`openclaw mcp add astock --command venv/bin/python --arg server.py`
- **Claude Desktop**：编辑 `claude_desktop_config.json`，写入 command + args
- **其他**（Cursor、pi 等）：同理，找到 MCP 配置入口填启动命令

配置完成后，在对话里说"查一下茅台"，AI 就会自动拉起服务器、调用工具、返回结果。验证方式：查看进程列表，那个 server.py 是被客户端自动拉起的。

## 真实踩坑三连

这次实战撞上的坑，比代码本身更有价值：

**① Python 版本坑**：系统自带 3.9，SDK 要求 3.10+，`pip` 报 "No matching distribution" 却不说明原因。教训：装不上先查版本。

**② 盘前数据坑**：上午 9 点测试，行情返回全零——不是 bug，是没开盘。免费接口的数据要考虑**时段状态**：盘前用昨收兜底、标注状态，而不是让用户看到一堆 0。

**③ 接口废弃坑**：搜索接口返回空值。与其死磕，不如换设计——改用本地股票列表做离线搜索，反而更快更稳。教训：**外部依赖挂了，先想"有没有更好的方案"，而不是"怎么修复它"**。

## 协议的本质：两段式

MCP 最精妙的设计，是把"发现"和"调用"分开：

- **发现阶段靠文字**：服务器告诉 AI 工具名 + docstring + 参数 Schema，AI **读懂文字**决定用不用
- **调用阶段靠结构**：严格 JSON 传参，程序直接执行

文字决定"AI 选不选它"，结构决定"调用不出错"。所以写工具时，docstring 不是注释，是协议的一部分——写得越清楚，AI 用得越准。

## 克制的艺术

MCP 可以无限扩展，但**工具越多，AI 的上下文越挤、选择越乱**。实践准则：

1. 按需添加，用到才写
2. 一个服务器聚焦一个领域
3. 重任务（批量数据、长计算）用异步模式：启动任务返回 ID，完成后推送

## 结语

从"MCP 是啥"到"我的服务器在服务真实查询"，30 分钟。这套东西的价值不在代码量（80 行），而在它给你一个**标准化的方式把任何能力接给 AI**——行情、数据库、文件、内部系统，逻辑完全一样。

工具函数你早就会写，MCP 只是给了它们一个所有人都能用的插口。
