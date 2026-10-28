# 自有素材库

素材库只索引，不移动、修改或删除原文件。它解决两个问题：

1. 找到旧素材补一个路牌、日落、脚步或空镜；
2. 知道某个镜头在哪些片子里用过，避免反复使用。

## 建库

```bash
STUDIO=skills/field-reel
python3 "$STUDIO/scripts/media_library.py" scan .
```

输出在 `studio/library/`：

- `library.json`：机器可读索引；
- `library.md`：可以直接搜索；
- `sheets/<id>.jpg`：每段视频均匀抽 6 帧的联系表。

扫描会跳过 `board/`、渲染缓存、已有成片、预览和封面，只补新增或发生变化的文件。

项目已经有剪辑方案时，把路线、段落、字幕和留用结果带进索引：

```bash
python3 "$STUDIO/scripts/media_library.py" enrich "<素材目录>"
```

## 标注

初次扫描后，分批看联系表，把以下字段写回 `library.json`：

- `title`：4–12 个字；
- `description`：画面里有什么、怎么动、光线怎样；
- `keywords`：地点、物体、动作；
- `mood`：舒缓、开阔、紧张、热闹等；
- `time_of_day`：早、午、傍晚、夜；
- `privacy`：路人脸、车牌、门牌、私人屏幕；
- `status`：`active` 或 `rejected`。

不要只信自动标签。标签用来找候选，最后必须看联系表。

重建可读索引：

```bash
python3 "$STUDIO/scripts/media_library.py" rebuild
```

## 搜索和使用记录

```bash
python3 "$STUDIO/scripts/media_library.py" search "日落 路牌"
python3 "$STUDIO/scripts/media_library.py" use <素材id> <项目名>
python3 "$STUDIO/scripts/media_library.py" reject <素材id>
```

选镜头时优先：内容匹配、没有隐私风险、没用过、较新、方向和成片一致。没有好镜头就不用，不能拿无关空镜凑数。

