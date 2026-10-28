# 实地成片

把一组实地拍摄收成 B 站成片：边走边说，或者风景旁白。先出可修改的剪辑方案，确认之后才剪切、压字幕、配乐、做封面，并做质检和投稿包。

不合成声音。口播用现场原话，旁白用本人录音或纯字幕。

## 技能

| 技能 | 作用 |
|---|---|
| `skills/field-reel` | 总流程：选题、拍摄、素材库、投稿和复盘 |
| `skills/bilibili-walk-talk` | 徒步、骑行、游玩、探店 |
| `skills/bilibili-scenic` | 风景和公路片 |
| `skills/bilibili-cut-core` | 共用的检查、方案页和渲染脚本 |

在 Cursor 里把 `skills/` 挂到项目技能目录后，提到剪视频、选题或投稿就会进入对应流程。

## 本地配置

公开仓库不包含账号和素材。克隆后在仓库根目录创建 `studio/local.json`：

```json
{
  "bilibili_mid": "你的空间 mid",
  "python": "python3"
}
```

再把 `studio/CHANNEL.example.md` 复制为 `studio/CHANNEL.md`，写下自己的账号定位。配乐台账从 `studio/rights/music.example.json` 复制为 `studio/rights/music.json`。

转写依赖本机的 [mlx-audio](https://github.com/Blaizzy/mlx-audio) SenseVoice。`python` 指向装有它的解释器；没有转写环境时不要猜文案。

素材、成片、方案页、素材库、播放快照和实验记录都留在本地，见 `.gitignore`。

## 常用命令

在仓库根目录执行：

```bash
python3 skills/bilibili-cut-core/scripts/probe_clips.py "素材目录"
python3 skills/bilibili-cut-core/scripts/footage_audit.py "素材目录"
python3 skills/field-reel/scripts/project.py init "素材目录" --style walk --date YYYY-MM-DD --route "路线名"
python3 skills/field-reel/scripts/qc_video.py "成片.mp4"
python3 skills/field-reel/scripts/account_snapshot.py
```

## 许可

代码使用 MIT License。技能里提到的字体、音乐和地图数据另有各自的许可，不因为本仓库而获得授权。
