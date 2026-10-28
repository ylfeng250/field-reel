#!/usr/bin/env python3
"""Build and search a non-destructive library of the creator's own footage."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / "studio" / "library"
INDEX = LIBRARY / "library.json"
SHEETS = LIBRARY / "sheets"

VIDEO = {".mp4", ".mov", ".m4v", ".mkv"}
PHOTO = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
SKIP_DIRS = {
    ".git", ".claude", ".agents", "skills", "studio", "board",
    "node_modules", "__pycache__", "render", "qc-frames",
}
SKIP_WORDS = ("粗剪", "成片", "预览", ".无声", "代理", "proxy")
LOCATION_KEYS = ("location", "com.apple.quicktime.location.ISO6709", "location-eng")


def ffprobe(path):
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffprobe 20 秒没有返回") from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "")[-500:])
    return json.loads(proc.stdout or "{}")


def captured_from_name(name):
    match = re.search(r"(20\d{6})[_-](\d{6})", name)
    if not match:
        return ""
    day, clock = match.groups()
    return f"{day[:4]}-{day[4:6]}-{day[6:8]}T{clock[:2]}:{clock[2:4]}:{clock[4:6]}"


def parse_location(tags):
    for key in LOCATION_KEYS:
        text = str(tags.get(key) or "").strip().strip("/")
        match = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", text)
        if match:
            return [float(match.group(1)), float(match.group(2))]
    return None


def skip_file(path):
    if path.name.startswith(".") or any(word in path.name for word in SKIP_WORDS):
        return True
    if path.stem == "封面":
        return True
    if path.suffix.lower() in VIDEO and path.with_suffix(".srt").exists():
        return True
    return False


def discover(source):
    found = []
    for current, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")]
        folder = Path(current)
        for name in files:
            path = folder / name
            if path.suffix.lower() not in VIDEO | PHOTO or skip_file(path):
                continue
            found.append(path.resolve())
    return sorted(found)


def media_info(path):
    data = ffprobe(path)
    fmt = data.get("format") or {}
    tags = fmt.get("tags") or {}
    width = height = 0
    duration = float(fmt.get("duration") or 0)
    audio = False
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and not width:
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
        elif stream.get("codec_type") == "audio":
            audio = True
    if path.suffix.lower() in PHOTO:
        try:
            with Image.open(path) as image:
                width, height = image.size
        except OSError:
            pass
    captured = captured_from_name(path.name) or tags.get("creation_time") or ""
    return {
        "kind": "video" if path.suffix.lower() in VIDEO else "photo",
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "orientation": "landscape" if width >= height else "portrait",
        "captured": captured,
        "gps": parse_location(tags),
        "has_audio": audio,
    }


def stable_id(path, source):
    try:
        relative = path.relative_to(source).as_posix()
    except ValueError:
        relative = str(path)
    digest = hashlib.sha1(relative.encode()).hexdigest()[:8]
    stem = re.sub(r"[^\w\u4e00-\u9fff]+", "-", path.stem, flags=re.UNICODE).strip("-").lower()
    return f"{stem[:36]}-{digest}"


def font(size):
    for path in (
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def label_sheet(path, title):
    image = Image.open(path).convert("RGB")
    canvas = Image.new("RGB", (image.width, image.height + 38), "black")
    canvas.paste(image, (0, 38))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), title[:80], font=font(18), fill="white")
    canvas.save(path, quality=88)


def make_sheet(item):
    dest = SHEETS / f"{item['id']}.jpg"
    source = Path(item["path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if item["kind"] == "photo":
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((960, 540), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (960, 540), (20, 20, 20))
                canvas.paste(image, ((960 - image.width) // 2, (540 - image.height) // 2))
                canvas.save(dest, quality=88)
        except OSError:
            return ""
    else:
        duration = max(0.1, float(item.get("duration") or 0.1))
        stamps = [duration * ratio for ratio in (0.08, 0.25, 0.42, 0.58, 0.75, 0.92)]
        cmd = ["ffmpeg", "-y", "-nostdin"]
        for stamp in stamps:
            cmd += ["-ss", f"{stamp:.3f}", "-i", str(source)]
        chains = [
            f"[{index}:v]scale=320:180:force_original_aspect_ratio=decrease,"
            f"pad=320:180:(ow-iw)/2:(oh-ih)/2:color=black[s{index}]"
            for index in range(6)
        ]
        chains += [
            "[s0][s1][s2]hstack=inputs=3[top]",
            "[s3][s4][s5]hstack=inputs=3[bottom]",
            "[top][bottom]vstack=inputs=2[out]",
        ]
        cmd += [
            "-filter_complex", ";".join(chains), "-map", "[out]",
            "-frames:v", "1", str(dest), "-loglevel", "error",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return ""
        if proc.returncode != 0:
            return ""
    label_sheet(dest, source.name)
    return dest.relative_to(ROOT).as_posix()


def read_index():
    if not INDEX.exists():
        return {"version": 1, "source_roots": [], "items": []}
    return json.loads(INDEX.read_text(encoding="utf-8"))


def write_index(data):
    LIBRARY.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rebuild_markdown(data)


def rebuild_markdown(data):
    rows = [
        "# 自有素材库",
        "",
        "状态 | id | 日期 | 时长 | 方向 | 地点 | 标题/文件 | 关键词 | 用于",
        "---|---|---|---:|---|---|---|---|---",
    ]
    for item in sorted(data.get("items") or [], key=lambda row: row.get("captured") or "", reverse=True):
        tags = item.get("tags") or {}
        title = tags.get("title") or Path(item["path"]).name
        keywords = "、".join(tags.get("keywords") or [])
        place = tags.get("place") or ""
        used = "、".join(item.get("used") or [])
        rows.append(
            f"{item.get('status', 'active')} | {item['id']} | {(item.get('captured') or '')[:10]} | "
            f"{float(item.get('duration') or 0):.1f}s | {item.get('orientation', '')} | {place} | "
            f"{title} | {keywords} | {used}"
        )
    (LIBRARY / "library.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def cmd_scan(args):
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        sys.exit(f"不是目录: {source}")
    data = read_index()
    old = {item["path"]: item for item in data.get("items") or []}
    paths = discover(source)
    if args.limit:
        paths = paths[: args.limit]
    changed = 0
    items = list(data.get("items") or [])
    positions = {item["path"]: index for index, item in enumerate(items)}
    for count, path in enumerate(paths, 1):
        stat = path.stat()
        previous = old.get(str(path))
        if previous and previous.get("size") == stat.st_size and previous.get("mtime") == int(stat.st_mtime):
            continue
        try:
            info = media_info(path)
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue
        item = {
            "id": previous["id"] if previous else stable_id(path, source),
            "path": str(path),
            "source_root": str(source),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            **info,
            "sheet": "",
            "tags": (previous or {}).get("tags"),
            "status": (previous or {}).get("status", "active"),
            "used": (previous or {}).get("used", []),
        }
        item["sheet"] = make_sheet(item)
        if str(path) in positions:
            items[positions[str(path)]] = item
        else:
            positions[str(path)] = len(items)
            items.append(item)
        changed += 1
        print(f"{count}/{len(paths)} {item['id']} {path.name}", flush=True)
    roots = set(data.get("source_roots") or [])
    roots.add(str(source))
    data.update(
        version=1,
        updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        source_roots=sorted(roots),
        items=items,
    )
    write_index(data)
    print(f"{len(items)} items, {changed} added/updated")
    print(INDEX)


def cmd_search(args):
    data = read_index()
    terms = [term.lower() for term in args.query.split() if term]
    ranked = []
    for item in data.get("items") or []:
        if item.get("status") != "active":
            continue
        haystack = json.dumps(item, ensure_ascii=False).lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            freshness = item.get("captured") or ""
            unused = 1 if not item.get("used") else 0
            ranked.append((score, unused, freshness, item))
    for _, _, _, item in sorted(ranked, reverse=True)[: args.limit]:
        tags = item.get("tags") or {}
        print(
            f"{item['id']}  {tags.get('title') or Path(item['path']).name}  "
            f"{item.get('duration', 0):.1f}s  used={','.join(item.get('used') or []) or '-'}"
        )
        print(f"  {item['path']}")
        print(f"  sheet: {ROOT / item['sheet'] if item.get('sheet') else '-'}")


def update_item(item_id, action, value=""):
    data = read_index()
    found = next((item for item in data.get("items") or [] if item["id"] == item_id), None)
    if not found:
        sys.exit(f"找不到素材 id: {item_id}")
    if action == "use" and value not in found.setdefault("used", []):
        found["used"].append(value)
    elif action == "reject":
        found["status"] = "rejected"
    elif action == "activate":
        found["status"] = "active"
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_index(data)
    print(f"{item_id} {action} {value}".strip())


def cmd_enrich(args):
    project = Path(args.project).expanduser().resolve()
    source = project / "edit-decision.json"
    if not source.exists():
        source = project / "board" / "analysis.json"
    if not source.exists():
        sys.exit("项目里没有 edit-decision.json 或 board/analysis.json")
    plan = json.loads(source.read_text(encoding="utf-8"))
    beats = {beat["id"]: beat.get("label") or "" for beat in plan.get("beats") or []}
    clips = {str((project / clip["file"]).resolve()): clip for clip in plan.get("clips") or []}
    data = read_index()
    changed = 0
    for item in data.get("items") or []:
        clip = clips.get(str(Path(item["path"]).resolve()))
        if not clip:
            continue
        label = beats.get(clip.get("beat") or "")
        route = plan.get("route") or project.name
        tags = item.get("tags") or {}
        tags.setdefault("title", " · ".join(part for part in (route, label) if part))
        tags.setdefault(
            "description",
            "。".join(
                part.strip("。 ")
                for part in (clip.get("note") or "", clip.get("subtitle") or "")
                if part.strip()
            ),
        )
        tags.setdefault("place", route)
        keywords = list(tags.get("keywords") or [])
        for value in (route, label):
            if value and value not in keywords:
                keywords.append(value)
        tags["keywords"] = keywords
        tags["selected_in_plan"] = bool(clip.get("keep"))
        item["tags"] = tags
        changed += 1
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_index(data)
    print(f"enriched {changed} items from {source}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("source")
    scan.add_argument("--limit", type=int, default=0)
    scan.set_defaults(func=cmd_scan)
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)
    rebuild = sub.add_parser("rebuild")
    rebuild.set_defaults(func=lambda _args: write_index(read_index()))
    use = sub.add_parser("use")
    use.add_argument("id")
    use.add_argument("project")
    use.set_defaults(func=lambda args: update_item(args.id, "use", args.project))
    reject = sub.add_parser("reject")
    reject.add_argument("id")
    reject.set_defaults(func=lambda args: update_item(args.id, "reject"))
    activate = sub.add_parser("activate")
    activate.add_argument("id")
    activate.set_defaults(func=lambda args: update_item(args.id, "activate"))
    enrich = sub.add_parser("enrich")
    enrich.add_argument("project")
    enrich.set_defaults(func=cmd_enrich)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
