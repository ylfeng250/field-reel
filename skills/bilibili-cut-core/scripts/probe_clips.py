#!/usr/bin/env python3
"""Inventory videos and photos. Writes board/inventory.json, thumbs, and wavs."""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

VIDEO = {".mp4", ".mov", ".m4v"}
IMAGE = {".jpg", ".jpeg", ".png", ".heic"}
HASH_NAME = re.compile(r"^[0-9a-f]{32}", re.I)
LOCATION_KEYS = ("location", "com.apple.quicktime.location.ISO6709", "location-eng")


def run_json(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:])
    return json.loads(proc.stdout or "{}")


def capture_from_name(name):
    match = re.search(r"(20\d{6})[_-](\d{6})", name)
    if not match:
        return None
    day, clock = match.group(1), match.group(2)
    return f"{day[:4]}-{day[4:6]}-{day[6:8]}T{clock[:2]}:{clock[2:4]}:{clock[4:6]}"


def skip(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if any(word in name for word in ("粗剪", "成片", "预览", ".无声")):
        return True
    if path.stem == "封面":
        return True
    if path.suffix.lower() in VIDEO and not name.startswith("VID_"):
        if path.with_suffix(".srt").exists():
            return True
    return False


def frame_rate(value):
    text = str(value or "0/1")
    if "/" not in text:
        return float(text or 0)
    numerator, denominator = text.split("/", 1)
    denominator = float(denominator or 0)
    return float(numerator) / denominator if denominator else 0.0


def probe_media(path: Path):
    data = run_json([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ])
    fmt = data.get("format") or {}
    tags = fmt.get("tags") or {}
    duration = float(fmt.get("duration") or 0)
    width = height = 0
    has_audio = False
    variable_rate = False
    hdr = False
    pixel_format = ""
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and not width:
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            rotate = (stream.get("tags") or {}).get("rotate")
            for side in stream.get("side_data_list") or []:
                rotate = rotate or side.get("rotation")
            if str(rotate or "0").lstrip("-") in {"90", "270"}:
                width, height = height, width
            average = frame_rate(stream.get("avg_frame_rate"))
            nominal = frame_rate(stream.get("r_frame_rate"))
            variable_rate = abs(average - nominal) > 0.5
            transfer = (stream.get("color_transfer") or "").lower()
            hdr = transfer in {"smpte2084", "arib-std-b67"}
            pixel_format = stream.get("pix_fmt") or ""
        if stream.get("codec_type") == "audio":
            has_audio = True
    created = tags.get("creation_time")
    if created and created.startswith("1970"):
        created = None
    return {
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "has_audio": has_audio,
        "creation_time": created,
        "encoder": tags.get("encoder") or "",
        "has_location": any(tags.get(key) for key in LOCATION_KEYS),
        "variable_frame_rate": variable_rate,
        "hdr": hdr,
        "pixel_format": pixel_format,
    }


def source_flags(path, meta, captured):
    flags = []
    if path.suffix.lower() in VIDEO:
        recompressed = meta["encoder"].startswith("Lavf") and max(meta["width"], meta["height"]) <= 1280
        if recompressed or HASH_NAME.match(path.stem):
            flags.append("wechat")
        if meta.get("variable_frame_rate"):
            flags.append("vfr")
        if meta.get("hdr"):
            flags.append("hdr")
        if meta.get("pixel_format") and meta["pixel_format"] != "yuv420p":
            flags.append(meta["pixel_format"])
    if not captured:
        flags.append("no_time")
    return flags


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: probe_clips.py <footage-dir>")
    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"不是目录: {root}")

    board = root / "board"
    thumbs = board / "thumbs"
    wavs = board / "wav"
    thumbs.mkdir(parents=True, exist_ok=True)
    wavs.mkdir(parents=True, exist_ok=True)

    found = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or skip(path):
            continue
        suffix = path.suffix.lower()
        if suffix in VIDEO or suffix in IMAGE:
            found.append(path)

    rows = []
    warnings = []
    for path in found:
        captured = capture_from_name(path.name)
        source = "filename" if captured else ""
        try:
            meta = probe_media(path)
        except (RuntimeError, json.JSONDecodeError) as exc:
            warnings.append(f"{path.name}: {exc}")
            continue
        if not captured and meta.get("creation_time"):
            captured = meta["creation_time"]
            source = "creation_time"
        rows.append({
            "path": path,
            "kind": "video" if path.suffix.lower() in VIDEO else "photo",
            "captured": captured or "",
            "time_source": source or "unknown",
            "flags": source_flags(path, meta, captured),
            **meta,
        })

    rows.sort(key=lambda row: (row["captured"] or "9999", row["path"].name))
    clips = []
    for index, row in enumerate(rows, 1):
        clip_id = f"c{index:02d}"
        path = row.pop("path")
        row.pop("encoder", None)
        thumb = thumbs / f"{clip_id}.jpg"
        mid = max(0, (row["duration"] or 0) * 0.45)
        thumb_cmd = ["ffmpeg", "-y", "-nostdin"]
        if row["kind"] == "video":
            thumb_cmd += ["-ss", f"{mid:.3f}"]
        thumb_cmd += [
            "-i", str(path), "-frames:v", "1",
            "-vf", "scale=640:-2", str(thumb),
            "-loglevel", "error",
        ]
        made = subprocess.run(thumb_cmd, capture_output=True, text=True)
        if made.returncode != 0:
            warnings.append(f"{path.name}: 缩略图失败")
        wav_rel = ""
        if row["kind"] == "video" and row["has_audio"]:
            wav = wavs / f"{clip_id}.wav"
            audio = subprocess.run([
                "ffmpeg", "-y", "-nostdin", "-i", str(path),
                "-vn", "-ac", "1", "-ar", "16000", str(wav),
                "-loglevel", "error",
            ], capture_output=True, text=True)
            if audio.returncode != 0:
                warnings.append(f"{path.name}: 音频失败")
            else:
                wav_rel = wav.relative_to(root).as_posix()
        clips.append({
            "id": clip_id,
            "file": path.name,
            "kind": row["kind"],
            "captured": row["captured"],
            "time_source": row["time_source"],
            "flags": row["flags"],
            "duration": row["duration"] if row["kind"] == "video" else 2.5,
            "width": row["width"],
            "height": row["height"],
            "has_audio": row["has_audio"],
            "has_location": row["has_location"],
            "thumb": thumb.relative_to(root).as_posix() if thumb.exists() else "",
            "wav": wav_rel,
            "speech": "",
        })

    videos = [clip for clip in clips if clip["kind"] == "video"]
    alerts = []
    wechat = [clip["file"] for clip in videos if "wechat" in clip["flags"]]
    untimed = [clip["file"] for clip in clips if "no_time" in clip["flags"]]
    if wechat:
        alerts.append(f"{len(wechat)}/{len(videos)} 段像微信转存（压到 720p 或文件名是哈希），先找原片再剪")
    if untimed:
        alerts.append(f"{len(untimed)} 个文件没有拍摄时间，按拍摄顺序排不了，要用口播内容或画面排")
    sizes = Counter(f"{clip['width']}x{clip['height']}" for clip in videos)
    if len(sizes) > 1:
        alerts.append("分辨率混在一起: " + ", ".join(f"{size}×{count}" for size, count in sizes.most_common()))

    out = {
        "root": str(root),
        "clips": clips,
        "map_available": sum(1 for clip in videos if clip["has_location"]) >= 3,
        "alerts": alerts,
        "warnings": warnings,
    }
    dest = board / "inventory.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"clips {len(clips)}")
    for clip in clips:
        clock = clip["captured"] or "?"
        mark = " ".join(clip["flags"])
        print(f"{clip['id']} {clip['kind']:5} {clip['duration']:7.1f}s {clip['width']}x{clip['height']} {clock} {clip['file']} {mark}".rstrip())
    if alerts:
        print("alerts")
        for item in alerts:
            print(" !", item)
    if warnings:
        print("warnings")
        for item in warnings:
            print(" -", item)
    print(dest)


if __name__ == "__main__":
    main()
