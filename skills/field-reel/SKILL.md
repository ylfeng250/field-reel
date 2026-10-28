---
name: field-reel
description: >-
  实地成片：把实地拍摄收成 B 站成片的总工作流。覆盖账号定位、选题、拍摄计划、素材库、边走边说或风景旁白剪辑、封面标题、版权、成片质检、投稿包和数据复盘。
  用户提到 B 站账号、选题、拍摄、素材整理、剪视频、封面、标题、投稿、发布、数据或复盘时使用。
  视频制作会路由到 bilibili-walk-talk 或 bilibili-scenic；不合成声音，只使用现场口播、本人后录音或纯字幕。
---

# 实地成片

这是总入口。账号只有两条内容主线：

1. **边走边说**：徒步、爬山、骑行、游玩路线、探店。现场口播是主线。
2. **风景旁白**：自驾公路、山野湖泊、城市夜景。画面是主角，先写完整旁白，再分到镜头。

先读仓库根目录的 `studio/CHANNEL.md`。没有就按 [studio/CHANNEL.example.md](../../studio/CHANNEL.example.md) 让用户补一份，不要替他发明账号。不要发明第三种常驻风格。转写和账号数据用 `studio/local.json`，这份文件不进公开仓库。

## 路由

- 分析账号、找选题、排内容：读 [strategy.md](strategy.md)。
- 准备去拍、问该拍什么：读 [shooting.md](shooting.md)。
- 收到一组素材：先跑素材体检，再按口播占比选择：
  - 一半以上保留段有清楚口播 → `bilibili-walk-talk`
  - 大部分是风景或车里音乐 → `bilibili-scenic`
- 管理旧素材、找一个日落/路牌/空镜：读 [library.md](library.md)。
- 成片、投稿、版权和验收：读 [delivery.md](delivery.md)。
- 分析播放、找异常高表现、做月度复盘：读 [analytics.md](analytics.md)。

## 项目状态

每期素材目录里维护 `project.json`。状态只能往前走：

`idea → footage → board → confirmed → preview → final → qc_passed → ready → published → reviewed`

用：

```bash
STUDIO=skills/field-reel
python3 "$STUDIO/scripts/project.py" init "<素材目录>" --style walk --date YYYY-MM-DD --route "路线名"
python3 "$STUDIO/scripts/project.py" status "<素材目录>" board
python3 "$STUDIO/scripts/project.py" show "<素材目录>"
```

`style` 只用 `walk` 或 `scenic`。不要把原始素材移走或改名。

## 固定闸门

- 素材体检有「疑似微信压缩」时，先让用户找原片。
- 没有页面里的 `confirmed: true`，不出成片。
- 风景片先出 720p 预览，确认节奏再出正式片。
- 正式片必须通过 `qc_video.py`，失败项没解决不能标记 `ready`。
- 投稿前由用户确认标题、封面、事实、音乐授权和隐私；不自动发布。
- 发布 7 天以后再做首轮数据判断，新片未跑满 7 天不判成败。

## 产品边界

- 不做声音克隆、TTS 或通用播音腔。旁白只选「本人录音」或「纯字幕」。
- 不用来源不明的音乐、影视片段、网图或他人视频。
- 自动检测只提供证据。黑场、定格、相似镜头和高运动量都可能是有意的，最终由画面复核决定。
- 公开 API 拿不到点击率、完播率、观众留存和涨粉来源；这些数据只能让用户从创作中心填入模板。

## 每次交付

给出：

1. 当前项目状态；
2. 新生成或修改的文件；
3. 自动检查结果与仍需人工确认的项目；
4. 下一步唯一最重要的动作。

