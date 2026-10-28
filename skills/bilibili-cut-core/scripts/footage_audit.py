#!/usr/bin/env python3
"""Measure raw footage quality and produce contact sheets.

Run after probe_clips.py:
  footage_audit.py <footage-dir> [--limit N]

Outputs board/footage-audit.json, board/素材体检.md and board/audit/sheets/.
Detections are review candidates, not automatic delete decisions.
"""

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size, index=0)
    except OSError:
        return ImageFont.load_default()


def run(cmd):
    proc = subprocess.run([str(part) for part in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "")[-1000:])
    return proc


def frame_metrics(path):
    with Image.open(path) as source:
        image = source.convert("L")
        if image.width > 8 and image.height > 8:
            image = image.crop((4, 4, image.width - 4, image.height - 4))
        stat = ImageStat.Stat(image)
        edges = image.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        small = image.resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(small.getdata())
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
        return {
            "brightness": round(stat.mean[0], 2),
            "contrast": round(stat.stddev[0], 2),
            "sharpness": round(edge_stat.var[0], 2),
            "dhash": f"{bits:016x}",
        }


def extract_frames(root, clip, frame_dir):
    source = root / clip["file"]
    target = frame_dir / clip["id"]
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    if clip.get("kind") == "photo":
        dest = target / "01.jpg"
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            image.save(dest, quality=88)
        return [dest]
    duration = max(0.1, float(clip.get("duration") or 0.1))
    run([
        "ffmpeg", "-y", "-nostdin", "-i", source,
        "-vf", f"fps={3 / duration:.8f},scale=640:-2",
        "-frames:v", "3", "-q:v", "3", target / "%02d.jpg", "-loglevel", "error",
    ])
    return sorted(target.glob("*.jpg"))


def make_sheet(frames, clip, dest):
    cells = []
    for path in frames:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((400, 225), Image.Resampling.LANCZOS)
            cell = Image.new("RGB", (400, 225), (18, 18, 18))
            cell.paste(image, ((400 - image.width) // 2, (225 - image.height) // 2))
            cells.append(cell)
    if not cells:
        return
    canvas = Image.new("RGB", (400 * len(cells), 270), (12, 12, 12))
    for index, cell in enumerate(cells):
        canvas.paste(cell, (400 * index, 45))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 10), f"{clip['id']}  {clip['file']}", font=font(20), fill="white")
    canvas.save(dest, quality=88)


def audio_metrics(path, duration):
    proc = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-i", str(path),
            "-af", "volumedetect,silencedetect=noise=-45dB:d=0.5",
            "-vn", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    mean = re.findall(r"mean_volume: (-?inf|-?[\d.]+) dB", proc.stderr)
    peak = re.findall(r"max_volume: (-?inf|-?[\d.]+) dB", proc.stderr)
    silences = [
        float(value)
        for value in re.findall(r"silence_duration: ([\d.]+)", proc.stderr)
    ]
    ratio = min(1.0, sum(silences) / duration) if duration else 0.0

    def value(found):
        if not found or found[-1] == "-inf":
            return None
        return float(found[-1])

    return {
        "mean_db": value(mean),
        "peak_db": value(peak),
        "silence_ratio": round(ratio, 3),
    }


def hamming(left, right):
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def similar_groups(rows, max_distance=5):
    parent = list(range(len(rows)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if hamming(rows[left]["dhash"], rows[right]["dhash"]) <= max_distance:
                union(left, right)
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault(find(index), []).append(row["id"])
    return [ids for ids in groups.values() if len(ids) > 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("footage")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    root = Path(args.footage).expanduser().resolve()
    inventory_path = root / "board" / "inventory.json"
    if not inventory_path.exists():
        sys.exit("先跑 probe_clips.py")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    clips = inventory.get("clips") or []
    if args.limit:
        clips = clips[: args.limit]

    audit = root / "board" / "audit"
    frame_dir = audit / "frames"
    sheet_dir = audit / "sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    hashes = []
    for index, clip in enumerate(clips, 1):
        try:
            frames = extract_frames(root, clip, frame_dir)
            measured = [frame_metrics(path) for path in frames]
        except (RuntimeError, OSError) as exc:
            print(f"{clip['id']} failed: {exc}", file=sys.stderr)
            continue
        make_sheet(frames, clip, sheet_dir / f"{clip['id']}.jpg")
        row = {
            "id": clip["id"],
            "file": clip["file"],
            "kind": clip.get("kind"),
            "duration": clip.get("duration"),
            "sheet": (sheet_dir / f"{clip['id']}.jpg").relative_to(root).as_posix(),
            "brightness": round(statistics.median(item["brightness"] for item in measured), 2),
            "contrast": round(statistics.median(item["contrast"] for item in measured), 2),
            "sharpness": round(statistics.median(item["sharpness"] for item in measured), 2),
            "warnings": list(clip.get("flags") or []),
        }
        middle = measured[len(measured) // 2]
        row["dhash"] = middle["dhash"]
        hashes.append({"id": row["id"], "dhash": row["dhash"]})
        if clip.get("kind") == "video" and clip.get("has_audio"):
            row["audio"] = audio_metrics(root / clip["file"], float(clip.get("duration") or 0))
        else:
            row["audio"] = None
        rows.append(row)
        print(f"{index}/{len(clips)} {clip['id']} sharp={row['sharpness']:.0f} light={row['brightness']:.0f}")

    sharp_values = [row["sharpness"] for row in rows]
    median_sharp = statistics.median(sharp_values) if sharp_values else 0
    sharp_floor = max(20.0, median_sharp * 0.35)
    for row in rows:
        if row["brightness"] < 38:
            row["warnings"].append("dark")
        elif row["brightness"] > 218:
            row["warnings"].append("overbright")
        if row["contrast"] < 18:
            row["warnings"].append("low_contrast")
        if row["sharpness"] < sharp_floor:
            row["warnings"].append("soft_candidate")
        audio = row.get("audio")
        if audio:
            if audio["peak_db"] is not None and audio["peak_db"] > -0.2:
                row["warnings"].append("audio_near_clip")
            if audio["mean_db"] is not None and audio["mean_db"] < -35:
                row["warnings"].append("audio_quiet")

    groups = similar_groups(hashes)
    payload = {
        "version": 1,
        "source": str(root),
        "summary": {
            "clips": len(rows),
            "median_sharpness": round(median_sharp, 2),
            "soft_threshold": round(sharp_floor, 2),
            "warning_clips": sum(bool(row["warnings"]) for row in rows),
        },
        "similar_candidates": groups,
        "clips": rows,
        "warning_note": "检测只提供候选；夜景、故意虚焦、照片定格和相邻车窗会产生合理告警。",
    }
    json_path = root / "board" / "footage-audit.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 素材体检",
        "",
        f"- 素材：{len(rows)} 段",
        f"- 清晰度中位数（相对值）：{median_sharp:.1f}",
        f"- 有告警：{payload['summary']['warning_clips']} 段",
        "",
        "> 这是筛选候选，不是自动删除。夜景、故意虚焦、照片和相邻车窗可能合理触发。",
        "",
        "## 需要先看",
        "",
        "| id | 文件 | 亮度 | 对比 | 清晰度 | 音频 | 告警 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    warned = [row for row in rows if row["warnings"]]
    for row in warned:
        audio = row.get("audio") or {}
        audio_text = (
            f"均值 {audio.get('mean_db')} / 峰值 {audio.get('peak_db')} dB"
            if audio else "—"
        )
        lines.append(
            f"| {row['id']} | {row['file']} | {row['brightness']:.0f} | "
            f"{row['contrast']:.0f} | {row['sharpness']:.0f} | {audio_text} | "
            f"{'、'.join(row['warnings'])} |"
        )
    if not warned:
        lines.append("| — | 没有机器告警 | — | — | — | — | — |")
    lines += ["", "## 相似镜头候选", ""]
    if groups:
        lines += ["- " + "、".join(group) for group in groups]
    else:
        lines.append("没有找到中间帧高度相似的组合。")
    lines += [
        "",
        "## 人工检查",
        "",
        "- 看 `board/audit/sheets/`：主体、路牌、菜单和隐私不能靠机器判断。",
        "- 相似候选只留变化更明显、构图更稳、说话更完整的一段。",
        "- `soft_candidate` 是相对整批素材的清晰度，不代表一定失焦。",
        "",
    ]
    md_path = root / "board" / "素材体检.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
