#!/usr/bin/env python3
"""每日 AI 资讯采集：中文媒体 + HF 论文热榜 + HN AI 热帖 + 海外媒体 → 中文日报

纯标准库，零依赖。任何数据源失败只跳过该源；GLM 翻译失败降级保留英文。
"""
import json
import os
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}
CTX = ssl.create_default_context()
DRY = "--dry-run" in sys.argv

GLM_BASE = os.environ.get("GLM_BASE", "https://open.bigmodel.cn/api/coding/paas/v4")
GLM_KEY = os.environ.get("GLM_API_KEY", "")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4.5-flash")


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def get_json(url):
    try:
        return json.loads(get(url))
    except Exception as e:
        print(f"[warn] {url}: {e}", file=sys.stderr)
        return None


def post_json(url, payload, headers, timeout=90):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read())


def glm_chat(system, user, retries=1):
    """调 GLM 翻译/摘要；429 限流时重试一次；失败返回 None（调用方自行降级）"""
    if not GLM_KEY:
        return None
    import time
    for attempt in range(retries + 1):
        try:
            data = post_json(
                f"{GLM_BASE}/chat/completions",
                {
                    "model": GLM_MODEL,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                {"Authorization": f"Bearer {GLM_KEY}"},
            )
            if "choices" in data:
                return (data["choices"] or [{}])[0].get("message", {}).get("content", "")
            err = data.get("error", {}).get("message", "")
            print(f"[warn] glm api: {err}", file=sys.stderr)
        except Exception as e:
            print(f"[warn] glm: {e}", file=sys.stderr)
        if attempt < retries:
            time.sleep(6)
    return None


def batch_translate(items):
    """items: [(title, link, score)] -> {link: (中文标题, 一句话导读)}；失败返回 {}"""
    if not items:
        return {}
    payload = json.dumps(
        [{"i": i, "t": t} for i, (t, l, _) in enumerate(items)],
        ensure_ascii=False,
    )
    raw = glm_chat(
        "你是科技媒体编辑。把英文 AI 资讯标题翻译成简体中文：术语准确（LLM=大模型, Agent=智能体, "
        "inference=推理, benchmark=基准测试, fine-tuning=微调），专有名词/产品名保留英文。"
        "同时为每条写一句话中文导读（15-30字，说明这事为什么值得关注，不要复述标题）。"
        '只输出 JSON 数组：[{"i":0,"zh":"中文标题","note":"一句话导读"}]，不要 markdown 代码块。',
        payload,
    )
    if not raw:
        return {}
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(0))
        out = {}
        for e in arr:
            i, zh, note = e.get("i"), e.get("zh", ""), e.get("note", "")
            if isinstance(i, int) and 0 <= i < len(items) and zh:
                out[items[i][1]] = (zh.strip(), (note or "").strip())
        return out
    except Exception as e:
        print(f"[warn] glm parse: {e}", file=sys.stderr)
        return {}


def hf_papers(limit=8):
    data = get_json("https://huggingface.co/api/daily_papers")
    out = []
    for p in (data or [])[:15]:
        paper = p.get("paper", p)
        title = (paper.get("title") or "").strip().replace("|", "\\|")
        pid = paper.get("id") or paper.get("arxiv_id") or ""
        ups = p.get("upvotes") or paper.get("upvotes") or 0
        if not title or not pid:
            continue
        out.append((title, f"https://huggingface.co/papers/{pid}", int(ups)))
        if len(out) >= limit:
            break
    return out


AI_KW = [
    "ai ", " ai", "llm", "gpt", "claude", "gemini", "openai", "anthropic",
    "deepmind", "machine learning", "neural", "transformer", "diffusion",
    "agent", "deepseek", "qwen", "llama", "mistral", "grok", "chatbot",
    "rag", "embedding", "copilot", "multimodal", "foundation model",
    "generative", "inference", "fine-tun",
]


def hn_ai(limit=8):
    ids = get_json("https://hacker-news.firebaseio.com/v0/topstories.json")
    items = []
    for i in (ids or [])[:80]:
        it = get_json(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        if not it or it.get("type") != "story":
            continue
        t = (it.get("title") or "").lower()
        if any(k in t for k in AI_KW):
            items.append((it["title"], f"https://news.ycombinator.com/item?id={it['id']}", it.get("score", 0)))
    items.sort(key=lambda x: -x[2])
    return items[:limit]


def rss(url, limit=6):
    out = []
    try:
        root = ET.fromstring(get(url))
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title and link:
                out.append((title, link, 0))
            if len(out) >= limit:
                break
    except Exception as e:
        print(f"[warn] rss {url}: {e}", file=sys.stderr)
    return out


def render_translated(items, zh_map, style="list", note=True):
    """渲染一个板块；有翻译用中文标题（附英文原题），没翻译保留英文"""
    lines = []
    for t, l, s in items:
        zh, note_txt = zh_map.get(l, ("", ""))
        if style == "table":
            row = f"| [{zh or t}]({l}) |"
            row += f" <br><small>{t}</small> |" if zh else f" {t} |"
            row += f" ⭐{s} |" if s else " |"
            if zh and note and note_txt:
                row = row[:-1] + f"<br><small>💡{note_txt}</small> |"
            if style == "table" and not zh and not s:
                row = f"| [{t}]({l}) |  |"
            lines.append(row)
        else:
            if zh:
                line = f"- **{zh}**（[原文]({l})）"
                if note and note_txt:
                    line += f" 💡{note_txt}"
                lines.append(line)
            else:
                suffix = f"（{s} 分）" if s else ""
                lines.append(f"- [{t}]({l}){suffix}")
    return "\n".join(lines)


def main():
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")

    sections = []

    # 1) 中文媒体（原生中文，无需翻译）
    cn_sources = [
        ("🇨🇳 中文媒体 · 量子位", "https://www.qbitai.com/feed"),
    ]
    for name, url in cn_sources:
        items = rss(url, 6)
        if items:
            sections.append((name, render_translated(items, {}, note=False)))

    # 2) HF 论文（英文 → GLM 翻译）
    papers = hf_papers()
    if papers:
        zh = batch_translate(papers)
        lines = []
        for t, l, u in papers:
            z, n = zh.get(l, ("", ""))
            if z:
                lines.append(f"| [{z}]({l}) <br><small>{t}</small> | ⭐{u}"
                             + (f" <br><small>💡{n}</small>" if n else "") + " |")
            else:
                lines.append(f"| [{t}]({l}) | ⭐{u} |")
        sections.append(("🧬 今日论文 · Hugging Face 热榜", "| 论文 | 热度 |\n|---|---|\n" + "\n".join(lines)))

    # 3) HN（英文 → GLM 翻译）
    h = hn_ai()
    if h:
        zh = batch_translate(h)
        sections.append(("🔥 社区热帖 · Hacker News", render_translated(h, zh)))

    # 4) 海外媒体（英文 → GLM 翻译）
    for name, url in [
        ("📰 海外媒体 · TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("📰 海外媒体 · VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ]:
        items = rss(url)
        if items:
            sections.append((name, render_translated(items, batch_translate(items))))

    if not sections:
        print("[fail] 所有数据源都失败，不生成日报", file=sys.stderr)
        sys.exit(1)

    # 5) GLM 生成今日总览
    overview = ""
    brief = "\n".join(t for t, _ in sections)
    raw = glm_chat(
        "你是科技媒体编辑，用简体中文写 2-3 句话的今日 AI 圈总览，点出当天主线趋势，语气平实，不要空洞形容词。",
        f"今日日报板块：\n{brief}\n\n部分头条：\n" + "\n".join(
            f"- {t}" for t, _ in [(papers[0][0], 0), (h[0][0], 0)] if papers or h)[:4]
    )
    if raw:
        overview = raw.strip().strip('"')

    fm = f"""---
title: "AI 日报 · {date_str}"
date: {now.strftime('%Y-%m-%d %H:%M:%S')} +0800
categories: [AI 日报]
tags: [日报]
permalink: /posts/ai-daily/{date_str}/
render_with_liquid: false
---

"""
    body = fm
    body += f"> 每日自动抓取生成 · 中文源：量子位 · 海外源（HF/HN/TechCrunch/VentureBeat）经 GLM 自动翻译\n\n"
    if overview:
        body += f"**今日看点**：{overview}\n\n"
    body += "\n\n".join(f"## {t}\n\n{c}\n" for t, c in sections)
    body += "\n\n---\n*本日报由 GitHub Actions 自动生成（GLM 中文化）。如某来源缺失说明该源当日抓取失败；海外条目翻译失败时保留英文原题。*\n"

    if DRY:
        print("=== DRY RUN 预览（前 2000 字）===")
        print(body[:2000])
        print(f"=== 共 {len(body)} 字节，{len(sections)} 个板块 ===")
        return

    path = Path(f"_posts/{date_str}-ai-daily.md")
    if path.exists():
        print("[skip] 今日日报已存在")
        return
    path.write_text(body, encoding="utf-8")
    print(f"[ok] 生成 {path}（{len(body)} 字节，{len(sections)} 个板块）")


if __name__ == "__main__":
    main()
