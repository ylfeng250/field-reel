# 共用流程

`bilibili-walk-talk` 和 `bilibili-scenic` 都用这里的脚本和方案页。下面的命令都在本目录下跑，素材目录记为 `$DIR`。

```bash
CORE=skills/bilibili-cut-core
PY="$(python3 -c 'import json; print(json.load(open("studio/local.json")).get("python","python3"))')"
```

## 闸门

- 没有 `$DIR/edit-decision.json`，或者里面 `confirmed` 不是 `true`，不出成片、不出封面。
- 对话里说「可以」「行」不算确认。用户要改故事、删段、改字、换配乐，改页面数据，让他再点一次「按这个剪」。确认之后他又在对话里改了某一段，先改 `edit-decision.json`，再渲染。
- 只有页面上有的选项才能进成片。缺了某个开关，先把它加到 `board/template.html` 和 `render_cut.py`，不要手改 JSON 绕过页面。
- 例外是预览：`render_cut.py --preview` 读草稿也能跑，只出 `board/render/预览.mp4`，不出封面和投稿包。

## 1. 摸素材

```bash
python3 $CORE/scripts/probe_clips.py "$DIR"
$PY $CORE/scripts/transcribe_clips.py "$DIR"
python3 $CORE/scripts/footage_audit.py "$DIR"
```

跳过：`*粗剪*`、`*成片*`、`*预览*`、`*.无声.*`、`封面.*`、`board/`，以及旁边有同名 `.srt`、文件名又不是 `VID_` 开头的成片。

`probe_clips.py` 打出 `alerts` 时先停，告诉用户：

- **像微信转存**：画质只剩 720p，拍摄时间也没了。让他从手机或微信里点「查看原视频」拿原片，放进同一个目录再重跑。剪完才发现会白做一轮。
- **没有拍摄时间**：顺序只能靠口播内容和画面推断，在方案里写明是推断的。
- **分辨率混在一起**：成片默认取时长占比最多的那档，不把 720p 硬拉成 4K。

`transcribe_clips.py` 失败就停，不要靠文件名猜内容。`audio_event` 是 `BGM` 的段多半是车里放的歌，听到的歌词不算口播，写进 `analysis.json` 时把这段的 `speech` 清空。

读 `board/inventory.json` 和 `board/素材体检.md`。先看体检告警和相似镜头候选；要认牌子、判断主体或隐私时，再看对应的 `board/audit/sheets/`，不要把每张图都读进上下文。

## 2. 方案页

写 `$DIR/board/analysis.json`，然后：

```bash
python3 $CORE/scripts/build_board.py "$DIR"
python3 $CORE/scripts/serve_board.py "$DIR"   # 放后台跑
```

把打印出来的地址用系统浏览器打开（`open http://127.0.0.1:8765/`）。这一步到此为止，等用户在页面上改完、点「按这个剪」。不要在对话里用长清单代替这个页面，也不要替他选旁白方式和配乐。

### analysis.json

顶层：

| 字段 | 说明 |
|---|---|
| `board_id` | 例 `ahe-20260930` |
| `style` | `walk` 边走边说，或 `scenic` 风景旁白 |
| `route`、`date` | 路线短名、`YYYY-MM-DD` |
| `title` | 按分支 style.md 里的标题格式 |
| `spine` | 一句话主线 |
| `approach` | 怎么剪，几句 |
| `description` | 可选，投稿简介正文。不写就用 `spine` |
| `tags` | 可选，B 站标签，4 到 5 个 |
| `beats[]` | `id`、`label`、`note`。成片会按段落生成章节时间点 |
| `clips[]` | 见下 |
| `covers[]` | 2 到 4 张：`id`、`file`、`kind`、`time`（视频取帧秒数）、`thumb`、`caption_top`（如 `10.17`）、`caption_bottom`（路线短名） |
| `map_available` | 从 inventory 抄过来。为 `true` 时页面才出现路线图开关 |
| `map_samples` | 可选，`route_map.py` 出的样图路径 |
| `map` | 可选，预填路线图：`title`、`from`、`to`、`km`（牌子上的全程公里数，不知道就留 0 按定位算） |
| `music_options[]` | 可选，配乐候选：`file`（放在 `board/music/`）、`title`、`source_url`、`license`、`license_url`、`credit`（投稿署名原文）、`note`（一句风格描述） |
| `field_volume`、`transition` | 可选，预填原声大小（1、0.3、0）和转场（`cut`、`black`）。不写就按分支默认 |
| `resolution` | 可选，强制成片分辨率，如 `1920x1080` |

不要预填 `voice_mode` 和 `music` 的选择，这两项由用户在页面上选。

`clips[]` 每段从 inventory 带上 `id`、`file`、`kind`、`captured`、`duration`、`width`、`height`、`thumb`、`speech`、`voiced`、`audio_event`，再补：

- `subtitle`：这段要出现的字，一句一行。有原话用原话，没原话就是旁白稿。
- `keep`、`beat`、`in_sec`、`out_sec`、`note`（留或丢的理由，短）。

## 3. 确认之后

先读 `$DIR/edit-decision.json`，`confirmed` 不是 `true` 就回到第 2 步。以这份文件为准，`analysis.json` 里的建议不能盖过它。

按 `voice_mode` 走：

- `field`：全是现场原话，直接渲染。
- `card`：旁白只上字幕，不出声，直接渲染。
- `self`：把要念的句子按页面顺序发给他，每段标上片段编号。等他把录音放进 `$DIR/board/voice/`，一段一个文件，文件名用片段编号（`c03.wav`）。他只给了一整条，就按停顿切开再放进去。

然后渲染：

```bash
python3 $CORE/scripts/render_cut.py "$DIR"             # 成片
python3 $CORE/scripts/render_cut.py "$DIR" --preview   # 720p 预览，快很多
```

渲染会自动处理这些，不要另写一套：

- **字幕**：每句单独上屏，一行最多 16 个字，最多两行，太长就在标点处拆成两屏。有现场口播的段按检测到的说话区间对时间；旁白段按配音长度或阅读速度（每秒 6 个字）分配。
- **旁白比画面长**：先把出点往后挪，素材不够再放慢画面（最多 1.35 倍），还不够才定格末帧。每段做了什么会打在日志里，要告诉用户。
- **配乐**：按成片长度循环，接缝处交叉淡化，开头淡入、结尾淡出。有人声的地方配乐自动压低约 10 dB；没有人声的片子配乐就是主角。
- **响度**：最后统一做两遍 loudnorm，到 -14 LUFS、真峰值 -1.5 dB，采样率 48 kHz。B 站播放端的音量均衡大约在 -12 到 -16 LUFS 之间，-14 两头都不吃亏。
- **缓存**：每段按内容算指纹，没改的段不重新编码。只改了一句字幕，就只重渲那一段。
- **封面和投稿包**：`封面.jpg`（1146×716）、同名 `.srt`、`投稿.md`、`publish.json`（标题、简介、章节、标签、配乐署名）都在 `$DIR`。

## 4. 交付前自查

1. 跑 `field-reel/scripts/qc_video.py`；有阻断项不能交付。
2. 看 `qc-frames/`：字幕有没有挡住脸和牌子，路线图有没有压住主体。
3. 渲染日志里有「放慢」「定格」的段，单独抽一帧确认看着不怪。
4. 告诉用户：成片路径、时长、标题，`投稿.md` 和 `质检报告.md` 在哪，以及哪些段被自动延长或放慢了。
5. 关掉 `serve_board.py`（pid 在 `board/server.txt`）。
