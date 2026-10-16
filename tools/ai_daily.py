#!/usr/bin/env python3
"""每日 AI 资讯采集：HF 论文热榜 + HN AI 热帖 + 媒体 RSS → 博客日报

纯标准库，零依赖。任何数据源失败只跳过该源，不影响整体。
"""
import json
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
UA = {"User-Agent": "Mozilla/5.0 (compatible; blog-ai-daily-bot)"}
CTX = ssl.create_default_context()


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


def hf_papers(limit=8):
    """Hugging Face Daily Papers：社区投票最高的 AI 论文"""
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
    """Hacker News 首页里 AI 相关的高分帖"""
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


def main():
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")

    sections = []

    papers = hf_papers()
    if papers:
        lines = ["| 论文 | 热度 |", "|---|---|"]
        for t, l, u in papers:
            lines.append(f"| [{t}]({l}) | ⭐{u} |")
        sections.append(("🧬 今日论文 · Hugging Face Daily Papers", "\n".join(lines)))

    h = hn_ai()
    if h:
        sections.append(("🔥 社区热帖 · Hacker News", "\n".join(f"- [{t}]({l})（{u} 分）" for t, l, u in h)))

    for name, url in [
        ("📰 科技媒体 · TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("📰 科技媒体 · VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ]:
        items = rss(url)
        if items:
            sections.append((name, "\n".join(f"- [{t}]({l})" for t, l, _ in items)))

    if not sections:
        print("[fail] 所有数据源都失败，不生成日报", file=sys.stderr)
        sys.exit(1)

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
    body += f"> 每日自动抓取生成 · 数据源：Hugging Face / Hacker News / TechCrunch / VentureBeat\n\n"
    body += "\n\n".join(f"## {t}\n\n{c}\n" for t, c in sections)
    body += "\n\n---\n*本日报由 GitHub Actions 自动生成，如某来源缺失说明该源当日抓取失败。*\n"

    path = Path(f"_posts/{date_str}-ai-daily.md")
    if path.exists():
        print("[skip] 今日日报已存在")
        return
    path.write_text(body, encoding="utf-8")
    print(f"[ok] 生成 {path}（{len(body)} 字节，{len(sections)} 个板块）")


if __name__ == "__main__":
    main()
