#!/usr/bin/env python3
"""每日财经日报：A股大盘行情 + 全球指数 + 财经要闻（GLM 筛选分类点评）

数据源：东方财富指数API / 华尔街见闻直播 / 新浪财经7x24（全部公开接口，无需key）
纯标准库。单源失败自动跳过；GLM 失败降级为原始时间线。
"""
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}
CTX = ssl.create_default_context()
DRY = "--dry-run" in sys.argv

GLM_BASE = os.environ.get("GLM_BASE", "https://open.bigmodel.cn/api/coding/paas/v4")
GLM_KEY = os.environ.get("GLM_API_KEY", "")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4.5-flash")

# 指数代码（新浪 hq.sinajs.cn：s_ 简要行情 / int_ 全球指数）
INDEXES = [
    ("s_sh000001", "上证指数"), ("s_sz399001", "深证成指"), ("s_sz399006", "创业板指"),
    ("s_sh000688", "科创50"), ("int_hangseng", "恒生指数"), ("int_dji", "道琼斯"),
    ("int_nasdaq", "纳斯达克"), ("int_sp500", "标普500"),
]


def get(url, timeout=20, referer=None):
    h = dict(UA)
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def get_json(url, referer=None):
    try:
        return json.loads(get(url, referer=referer))
    except Exception as e:
        print(f"[warn] {url}: {e}", file=sys.stderr)
        return None


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return unescape(s).strip()


# ---------- 数据源 ----------

import subprocess


def em_indexes():
    """新浪行情指数（GBK文本，走 curl 子进程最稳）：[(名称, 点位, 涨跌幅%)]"""
    codes = ",".join(c for c, _ in INDEXES)
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", "15", "-A", UA["User-Agent"],
             "-H", "Referer: https://finance.sina.com.cn",
             f"https://hq.sinajs.cn/list={codes}"],
            capture_output=True, timeout=20)
        text = r.stdout.decode("gbk", errors="replace")
    except Exception as e:
        print(f"[warn] sina hq: {e}", file=sys.stderr)
        return []
    out = []
    for line in text.splitlines():
        m = re.match(r'var hq_str_\w+="([^"]*)"', line.strip())
        if not m:
            continue
        parts = m.group(1).split(",")
        if len(parts) < 4:
            continue
        try:
            out.append((parts[0], float(parts[1]), float(parts[3])))
        except ValueError:
            continue
    return out


def wallstcn(limit=40):
    """华尔街见闻直播：[(文本, 链接)]，A股市/宏观优先"""
    data = get_json("https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=" + str(limit))
    out = []
    for it in ((data or {}).get("data") or {}).get("items") or []:
        text = strip_html(it.get("content"))
        uri = (it.get("uri") or "").strip()
        if uri.startswith("http"):
            link = uri
        else:
            uid = uri.replace("wallstreetcn://live/", "").replace("wallstreetcn://livenews/", "")
            link = f"https://wallstreetcn.com/lives/{uid}" if uid else ""
        if text:
            out.append((text, link))
    return out


def sina_7x24(page_size=40):
    """新浪财经7x24快讯：[文本]"""
    data = get_json(f"https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size={page_size}&zhibo_id=152")
    out = []
    feed = ((data or {}).get("result") or {}).get("data") or {}
    for it in feed.get("feed", {}).get("list") or []:
        text = strip_html(it.get("rich_text"))
        if text:
            out.append(text)
    return out


# ---------- GLM ----------

def glm_chat(system, user, retries=1):
    if not GLM_KEY:
        return None
    import time
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{GLM_BASE}/chat/completions",
                data=json.dumps({
                    "model": GLM_MODEL, "temperature": 0.2,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                }).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {GLM_KEY}"})
            with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
                data = json.loads(r.read())
            if "choices" in data:
                return (data["choices"] or [{}])[0].get("message", {}).get("content", "")
            print(f"[warn] glm: {data.get('error', {}).get('message')}", file=sys.stderr)
        except Exception as e:
            print(f"[warn] glm: {e}", file=sys.stderr)
        if attempt < retries:
            time.sleep(6)
    return None


def glm_curate(news, indexes_line):
    """GLM 筛选+分类+点评。返回 (总览, [(分类, 标题, 点评, 原文, 链接)]) 或 None"""
    payload = json.dumps(
        {"大盘": indexes_line,
         "新闻": [{"i": i, "t": t[:160], "l": l} for i, (t, l) in enumerate(news)]},
        ensure_ascii=False,
    )
    raw = glm_chat(
        "你是资深A股财经编辑。从原始快讯中筛选出对A股投资者最重要的8~14条（政策、宏观、行业、重要公司、"
        "海外市场、大宗商品都覆盖，剔除广告软文和鸡毛蒜皮）。"
        "每条给：cat分类（宏观政策/行业动向/公司要闻/海外市场/大宗商品 之一）、t精炼中文标题（20字内）、"
        "d一句话点评（为什么重要/对A股什么影响，25字内）。"
        "再写 overview：今日财经主线总览2~3句（结合大盘数据）。"
        '只输出JSON：{"overview":"...","items":[{"i":0,"cat":"...","t":"...","d":"..."}]}，不要markdown代码块。',
        payload,
    )
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        items = []
        for e in d.get("items", []):
            i = e.get("i")
            if isinstance(i, int) and 0 <= i < len(news) and e.get("t"):
                t, l = news[i]
                items.append((e.get("cat", "要闻"), e["t"], e.get("d", ""), t, l))
        return (d.get("overview", ""), items) if items else None
    except Exception as e:
        print(f"[warn] glm parse: {e}", file=sys.stderr)
        return None


def main():
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")
    weekday = "一二三四五六日"[now.weekday()]

    # 1) 行情
    idx = em_indexes()
    idx_line = ""
    if idx:
        cells = "| 指数 | 点位 | 涨跌幅 |\n|---|---|---|\n"
        for name, val, pct in idx:
            arrow = "🔴" if pct < 0 else "🟢"
            cells += f"| {name} | {val:,.2f} | {arrow} {pct:+.2f}% |\n"
        idx_line = "；".join(f"{n} {p:+.2f}%" for n, _, p in idx)
        idx_md = cells
    else:
        idx_md = ""

    # 2) 新闻源
    news = []
    seen = set()
    for t, l in wallstcn():
        k = t[:30]
        if k not in seen:
            seen.add(k)
            news.append((t, l))
    for t in sina_7x24():
        k = t[:30]
        if k not in seen:
            seen.add(k)
            news.append((t, ""))

    if not idx and not news:
        print("[fail] 行情与新闻源全部失败", file=sys.stderr)
        sys.exit(1)

    # 3) GLM 筛选点评
    curated = glm_curate(news, idx_line or "（行情数据缺失）") if news else None

    fm = f"""---
title: "财经日报 · {date_str}"
date: {now.strftime('%Y-%m-%d %H:%M:%S')} +0800
categories: [财经日报]
tags: [日报, 股票, 财经]
permalink: /posts/finance-daily/{date_str}/
render_with_liquid: false
---

"""
    body = fm
    body += f"> 每日自动生成（周{weekday}）· 数据：新浪财经 / 华尔街见闻 · GLM 筛选点评\n\n"

    if idx_md:
        body += f"## 📊 大盘与全球指数\n\n{idx_md}\n\n"
    if curated:
        ov, items = curated
        if ov:
            body += f"**今日主线**：{ov}\n\n"
        body += "## 📰 要闻精选\n\n"
        cat_order = ["宏观政策", "行业动向", "公司要闻", "海外市场", "大宗商品"]
        def cat_rank(c):
            c = (c or "").strip()
            if c in cat_order:
                return cat_order.index(c)
            if "政策" in c or "宏观" in c:
                return 0
            if "公司" in c:
                return 2
            if "海外" in c or "外盘" in c:
                return 3
            if "大宗" in c or "商品" in c:
                return 4
            return 1
        groups = {}
        for cat, t, d, _, l in items:
            groups.setdefault(cat_rank(cat), []).append((cat, t, d, _, l))
        for rank in sorted(groups):
            first = groups[rank][0]
            body += f"### {first[0]}\n\n"
            for cat, t, d, _, l in groups[rank]:
                line = f"- **{t}**"
                if d:
                    line += f" —— {d}"
                if l:
                    line += f"（[原文]({l})）"
                body += line + "\n"
        body += "\n"
    elif news:
        body += "## 📰 快讯时间线（GLM 筛选失败，降级为原始流）\n\n"
        body += "\n".join(f"- {t}" for t, _ in news[:25]) + "\n\n"

    body += "---\n*本日报由 GitHub Actions 自动生成，仅供参考，不构成投资建议。*\n"

    if DRY:
        print("=== DRY RUN（前 2500 字）===")
        print(body[:2500])
        print(f"=== 共 {len(body)} 字节；行情{len(idx)}项，新闻源{len(news)}条 ===")
        return

    path = Path(f"_posts/{date_str}-finance-daily.md")
    if path.exists():
        print("[skip] 今日财经日报已存在")
        return
    path.write_text(body, encoding="utf-8")
    print(f"[ok] 生成 {path}（{len(body)} 字节）")


if __name__ == "__main__":
    main()
