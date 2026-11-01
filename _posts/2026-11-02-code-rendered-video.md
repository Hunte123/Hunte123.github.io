---
title: 用代码「手绘」一支有声短片：PIL + ffmpeg 零成本视频流水线
date: 2026-11-02 00:15:00 +0800
categories: [视频工程]
tags: [Python, ffmpeg, PIL, 视频生成]
render_with_liquid: false
---

昨晚我做了支 38 秒的小短片：火柴人捡到一颗坠落的星星，发现它的光越来越弱，于是翻山越岭把它举上山顶，看它重新亮起来、飞回夜空。有画面、有配音、有字幕、有钢琴配乐。

这支片子**没有用任何 AI 视频模型**，没花一分钱 API 额度：Python 手绘 912 帧，系统自带 TTS 配音，ffmpeg 合成混音，从写第一行代码到出片约两小时。

这篇文章把这条「代码渲染」路线完整拆开——技术栈、五步流程、三个踩坑、以及怎么复用到你自己的项目。看完你会发现：**做视频的门槛不在工具，在于想到「原来还能这么做」**。

## 先建立一个认知：视频就是三样东西

```text
视频 = 图片序列 + 音轨 + 时间轴
```

- 能用代码画图 → 就能生成每一帧
- 能调用 TTS → 就有配音
- ffmpeg 负责把一切缝起来

所有「程序做视频」的本质就是这一句。AI 生成的视频再神奇，落到文件层面也是这么个结构，只不过那些帧是模型算出来的，这里的帧是我们自己画的。

## 技术栈：全部免费

| 环节 | 工具 | 成本 |
| --- | --- | --- |
| 帧渲染 | Python + Pillow | 0 |
| 配音 | macOS `say`（换任意 TTS 均可） | 0 |
| 字幕 | 渲染时直接画进帧里 | 0 |
| BGM | incompetech / mixkit 免费曲库 | 0 |
| 合成混音 | ffmpeg | 0 |

Windows 用户把 `say` 换成 Edge-TTS 或任何 TTS 命令行，其余流程完全一致。

## 五步流程

### 第 1 步：分镜表（整个项目最重要的文件）

先不写渲染代码，先把时间轴写清楚。我的分镜表长这样：

```text
0-3s    标题淡入「一颗星星的回家路」
3-7s    流星坠落，落地成一颗微光小星
7-11s   火柴人走来，捡起星星捧在手心
11-14s  星光变弱闪烁，火柴人头上升起问号
14-22s  火柴人奔跑翻山（背景滚动）
22-27s  爬上山顶，双手把星星举向天空
27-32s  星星复活升空，光环扩散
32-38s  挥手告别 + 金句字幕
```

在代码里它就是一张 `(起始秒, 结束秒, 内容)` 的表，同时驱动画面、字幕、配音三个环节。**改片子 = 改这张表**，这是整条流水线可复用的关键。

### 第 2 步：逐帧渲染（Pillow）

渲染主循环只有一个 `for`：

```python
W, H, FPS = 1280, 720, 24
for fi in range(TOTAL_SEC * FPS):
    t = fi / FPS                      # 当前时间（秒）
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img, "RGBA")
    if t < 3:   draw_title(d, t)      # 按分镜表分发
    elif t < 7: draw_meteor(d, t)
    elif t < 11: draw_pickup(d, t)
    # ...每个分镜一个绘制函数
    img.save(f"frames/{fi:04d}.png")
```

角色本体是一个函数，姿势 = 一组关节角度：

```python
def stickman(d, cx, cy, lean=0, l_arm=40, r_arm=40, l_leg=15, r_leg=15):
    """头=圆圈，身体=线段，四肢=按角度画的线段"""
    # hip → neck → head，肩部出发按角度画手臂，髋部出发画腿
```

动画就是帧与帧之间插值角度，配一个 smoothstep 缓动：

```python
def lerp(a, b, t):  return a + (b - a) * t
def ease(t):        return t * t * (3 - 2 * t)

lean = lerp(0, 20, ease(t / 2))     # 2秒内身体前倾20度
```

走路、奔跑这类循环动作，让关节角度按正弦摆动即可：

```python
ph = ft * 11 * math.pi
l_leg, r_leg = 30 * math.sin(ph), 30 * math.sin(ph + math.pi)  # 双腿交替
```

912 帧渲染约 2 分钟（M 系芯片），改完直接全量重渲，不用做增量优化。

### 第 3 步：配音，逐句贴时间轴

每句旁白单独生成，再按分镜表的时间点贴到音轨上：

```bash
# 生成（每句一个文件）
say -v Tingting -r 205 -o line0.aiff "这是火柴人，和一颗星星的故事"

# 贴时间轴并合并（adelay 单位是毫秒）
ffmpeg -i n0.wav -i n1.wav ... -i n7.wav -filter_complex \
  "[0:a]adelay=500|500[a0];[1:a]adelay=3600|3600[a1];\
   [a0][a1]...amix=inputs=8:normalize=0,volume=1.7[out]" \
  -map "[out]" narration.wav
```

逐句生成的好处：时间完全由你控制，某一句不满意只重做那一句。

### 第 4 步：BGM——本流程最大的坑

错误做法（我的第一版）：

```bash
ffmpeg -i bgm.mp3 -af "volume=0.22" ...   # 直接乘系数
```

结果成片里音乐完全听不见。用 volumedetect 一测：钢琴曲本身是弱奏（mean -36 dB），再乘 0.22，而旁白是 -19 dB——**差了 16 dB，等于没有音乐**。

正确做法是响度归一化，把 BGM 拉到背景乐的标准位：

```bash
ffmpeg -i bgm.mp3 -t 38.5 -af \
  "loudnorm=I=-24:TP=-2:LRA=7,afade=t=in:st=0:d=0.8,afade=t=out:st=35.5:d=3" \
  bgm.wav
```

`I=-24 LUFS` 是背景乐的常用响度：清晰可闻，又不盖人声。混完别忘了验证——挑一段没有旁白的时段测响度：

```bash
ffmpeg -ss 19 -t 2.5 -i final.mp4 -vn -af volumedetect -f null -
# 修正后 mean -25 dB（修正前 -35 dB）
```

**记住这个数字直觉：人声轨 mean 约 -19 dB 时，BGM 归一到 -24 LUFS 刚好。**

### 第 5 步：合成

```bash
ffmpeg -framerate 24 -i frames/%04d.png -i final_audio.wav \
  -c:v libx264 -pix_fmt yuv420p -crf 23 \
  -c:a aac -b:a 128k -shortest -movflags +faststart out.mp4
```

图片序列 → H.264，加 `-movflags +faststart` 让微信、网页打开就播。

## 三个踩坑实录

1. **BGM 音量坑**（上面详述）：背景乐必须 `loudnorm`，不能拍脑袋乘系数。修正后音量提升 10 dB，钢琴声立刻「存在」了。
2. **ffmpeg 没编 drawtext**：不想重编 ffmpeg，字幕干脆用 PIL 画进帧里——反而因祸得福：字幕的时机、描边、透明度全是 Python 逻辑，和画面同一套时间轴，精确可控。
3. **音色坑**：macOS 系统里 Eddy、Grandpa 这些新音色列表里看得到但实际是空壳（`say` 出来是空音频），只有 Tingting 是完整安装的。用之前先测一句，看输出时长是否正常。

## 怎么复用：换一支片子，只改两处

1. **分镜表**：新的时间轴 + 每段画面描述
2. **旁白文案**：TTS 的输入文本

渲染循环、角色骨架、TTS 贴轨、混音、合成命令——全部原封不动。

这条流水线适合做的：

- 片头 / 片尾动画、Logo 动效
- 字幕特效（卡点歌词、知识点强调）
- 数据可视化视频（图表动画 + 旁白讲解）
- 节日祝福片、产品功能演示

以及一个定位判断：**AI 视频模型负责「画不出来的」（人物实拍感、复杂场景），代码渲染负责「必须精确的」（字幕时机、图形规则、批量复用）**。真正的生产管线是两条腿走路：AI 出素材，代码做包装。

## 收尾

整条流水线的全部家当：约 100 行 Python（渲染 + 字幕）+ 5 条 ffmpeg 命令（TTS 转码、贴轨合并、BGM 归一、混音、合成）+ 1 张分镜表。

下一次再看到「AI 视频生成」的新闻时，记得还有这么一条安静的路线：不抽卡、不限量、零成本，改一行代码就生效——适合所有「精确比惊艳重要」的视频场景。
