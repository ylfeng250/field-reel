#!/usr/bin/env python3
"""Draw a navigation card from the footage GPS track and stamp it on a frame."""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
LOCATION_KEYS = ("location", "com.apple.quicktime.location.ISO6709", "location-eng")
YELLOW = (244, 227, 74, 255)
MINT = (126, 232, 176, 255)
INK = (244, 247, 244, 255)
MUTED = (186, 198, 192, 255)
AHEAD = (214, 224, 220, 150)


def font(size):
    for index in (2, 1, 0):
        try:
            return ImageFont.truetype(FONT_PATH, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def parse_location(value):
    text = (value or "").strip().strip("/")
    if len(text) < 3:
        return None
    for index in range(1, len(text)):
        if text[index] in "+-":
            try:
                return float(text[:index]), float(text[index:])
            except ValueError:
                return None
    return None


def haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def probe_location(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    tags = (data.get("format") or {}).get("tags") or {}
    for key in LOCATION_KEYS:
        found = parse_location(tags.get(key))
        if found:
            return found
    return None


def ordered_videos(root):
    inventory = root / "board" / "inventory.json"
    if inventory.exists():
        clips = json.loads(inventory.read_text()).get("clips") or []
        return [root / clip["file"] for clip in clips if clip.get("kind") == "video" and clip.get("has_location", True)]
    return sorted(root.glob("VID_*.mp4"))


def load_track(root, refresh=False):
    root = Path(root)
    cache = root / "board" / "track.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    points = []
    for path in ordered_videos(root):
        found = probe_location(path)
        if not found:
            continue
        lat, lon = found
        points.append({"file": path.name, "lat": lat, "lon": lon})
    along = 0.0
    previous = None
    for point in points:
        here = (point["lat"], point["lon"])
        if previous is not None:
            along += haversine(previous, here)
        point["along_km"] = round(along, 3)
        previous = here
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(points, ensure_ascii=False, indent=2))
    return points


def snap(track, lat, lon):
    here = (lat, lon)
    best = min(range(len(track)), key=lambda index: haversine(here, (track[index]["lat"], track[index]["lon"])))
    return best


def project(track):
    lats = [point["lat"] for point in track]
    lons = [point["lon"] for point in track]
    mid = sum(lats) / len(lats)
    cos = math.cos(math.radians(mid))

    def xy(lat, lon):
        return lon * cos, lat

    raw = [xy(point["lat"], point["lon"]) for point in track]
    min_x, max_x = min(p[0] for p in raw), max(p[0] for p in raw)
    min_y, max_y = min(p[1] for p in raw), max(p[1] for p in raw)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    return raw, min_x, min_y, span_x, span_y


def draw_card(track, lat, lon, clock, card_w, card_h, info):
    scale = 2
    width, height = card_w * scale, card_h * scale
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = 36 * scale
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=(14, 24, 34, 214))
    draw.rounded_rectangle((scale, scale, width - 1 - scale, height - 1 - scale), radius=radius, outline=(126, 232, 176, 90), width=max(2, scale))

    pad = 28 * scale
    title = font(34 * scale)
    sub = font(20 * scale)
    stat = font(26 * scale)
    label = font(18 * scale)
    start_name = info.get("from") or ""
    end_name = info.get("to") or ""
    draw.text((pad, 22 * scale), info.get("title") or "", font=title, fill=YELLOW)
    if clock:
        tick = font(22 * scale)
        draw.text((width - pad, 28 * scale), clock, font=tick, fill=MINT, anchor="ra")
    if start_name or end_name:
        draw.text((pad, 64 * scale), f"{start_name}  →  {end_name}", font=sub, fill=MUTED)
    draw.line((pad, 102 * scale, width - pad, 102 * scale), fill=(255, 255, 255, 36), width=scale)

    footer_top = height - 108 * scale
    map_box = (pad, 118 * scale, width - pad, footer_top - 16 * scale)
    raw, min_x, min_y, span_x, span_y = project(track)
    map_w = map_box[2] - map_box[0]
    map_h = map_box[3] - map_box[1]
    fit = min(map_w / span_x, map_h / span_y) * 0.72
    origin_x = (map_box[0] + map_box[2]) / 2
    origin_y = (map_box[1] + map_box[3]) / 2
    center_x = min_x + span_x / 2
    center_y = min_y + span_y / 2

    def pix(point):
        x = origin_x + (point[0] - center_x) * fit
        y = origin_y - (point[1] - center_y) * fit
        return x, y

    pixels = [pix(point) for point in raw]
    index = snap(track, lat, lon)
    route = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    route_draw = ImageDraw.Draw(route)
    halo = max(10 * scale, 8)
    line = max(5 * scale, 4)
    if len(pixels) >= 2:
        route_draw.line(pixels, fill=(0, 0, 0, 90), width=halo, joint="curve")
        route_draw.line(pixels, fill=AHEAD, width=line, joint="curve")
        if index >= 1:
            route_draw.line(pixels[: index + 1], fill=YELLOW, width=line + scale, joint="curve")
    image.alpha_composite(route)

    start, end = pixels[0], pixels[-1]
    draw = ImageDraw.Draw(image)
    draw.ellipse((start[0] - 5 * scale, start[1] - 5 * scale, start[0] + 5 * scale, start[1] + 5 * scale), fill=INK)
    draw.ellipse((end[0] - 6 * scale, end[1] - 6 * scale, end[0] + 6 * scale, end[1] + 6 * scale), outline=MINT, width=max(2, scale))
    draw.text((start[0] - 12 * scale, start[1] + 10 * scale), start_name, font=label, fill=INK, anchor="rt")
    draw.text((end[0] + 12 * scale, end[1] - 8 * scale), end_name, font=label, fill=MINT, anchor="lb")

    here = pixels[index]
    nxt = here
    for step in range(index + 1, len(pixels)):
        if haversine((track[index]["lat"], track[index]["lon"]), (track[step]["lat"], track[step]["lon"])) >= 0.4:
            nxt = pixels[step]
            break
    if nxt == here and index + 1 < len(pixels):
        nxt = pixels[-1]
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_r = 16 * scale
    glow_draw.ellipse((here[0] - glow_r, here[1] - glow_r, here[0] + glow_r, here[1] + glow_r), fill=(126, 232, 176, 150))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6 * scale)))
    draw.ellipse((here[0] - 8 * scale, here[1] - 8 * scale, here[0] + 8 * scale, here[1] + 8 * scale), fill=(255, 255, 255, 255))
    draw.ellipse((here[0] - 5 * scale, here[1] - 5 * scale, here[0] + 5 * scale, here[1] + 5 * scale), fill=MINT)

    dx, dy = nxt[0] - here[0], nxt[1] - here[1]
    norm = math.hypot(dx, dy) or 1.0
    ux, uy = dx / norm, dy / norm
    px, py = -uy, ux
    tip = (here[0] + ux * 26 * scale, here[1] + uy * 26 * scale)
    back = (here[0] + ux * 13 * scale, here[1] + uy * 13 * scale)
    wing = 7 * scale
    left = (back[0] + px * wing, back[1] + py * wing)
    right = (back[0] - px * wing, back[1] - py * wing)
    draw.polygon([tip, left, right], fill=YELLOW)

    total = track[-1]["along_km"] or 1
    signed = float(info.get("km") or 0) or total
    done = signed * track[index]["along_km"] / total
    left_km = max(0.0, signed - done)
    base = footer_top
    draw.line((pad, base, width - pad, base), fill=(255, 255, 255, 36), width=scale)
    draw.text((pad, base + 18 * scale), "已走", font=sub, fill=MUTED)
    digits = 1 if signed < 20 else 0
    draw.text((pad, base + 44 * scale), f"{done:.{digits}f} km", font=stat, fill=YELLOW)
    draw.text((width - pad, base + 18 * scale), "剩余", font=sub, fill=MUTED, anchor="ra")
    draw.text((width - pad, base + 44 * scale), f"{left_km:.{digits}f} km", font=stat, fill=INK, anchor="ra")

    return image.resize((card_w, card_h), Image.Resampling.LANCZOS)


def card_layer(width, height, track, lat, lon, clock, info):
    card_w = max(280, int(width * 0.23))
    card_h = max(360, int(card_w * 1.28))
    card = draw_card(track, lat, lon, clock, card_w, card_h, info)
    margin = max(28, int(width * 0.028))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(card, (width - card_w - margin, margin), card)
    return layer


def stamp(image, track, lat, lon, clock, info):
    if not track:
        return image
    base = image.convert("RGBA")
    base.alpha_composite(card_layer(base.width, base.height, track, lat, lon, clock, info))
    return base


def preview(root, info):
    root = Path(root)
    track = load_track(root, refresh=True)
    if len(track) < 3:
        sys.exit("带定位的片段不到 3 段，画不了路线图")
    picks = sorted({0, len(track) // 3, len(track) * 2 // 3, len(track) - 1})
    dest = root / "board" / "map-preview"
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.jpg"):
        old.unlink()
    for index in picks:
        point = track[index]
        name = point["file"]
        frame = dest / "_frame.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1", "-i", str(root / name), "-frames:v", "1", str(frame), "-loglevel", "error"],
            check=True,
        )
        clock = ""
        match = re.search(r"20\d{6}[_-](\d{2})(\d{2})", name)
        if match:
            clock = f"{match.group(1)}:{match.group(2)}"
        image = stamp(Image.open(frame), track, point["lat"], point["lon"], clock, info)
        out = dest / f"{Path(name).stem}.jpg"
        image.resize((1600, int(1600 * image.height / image.width)), Image.Resampling.LANCZOS).convert("RGB").save(out, quality=90)
        frame.unlink()
        print(out.relative_to(root).as_posix())


if __name__ == "__main__":
    if len(sys.argv) not in (2, 6):
        sys.exit("usage: route_map.py <footage-dir> [标题 起点 终点 公里数]")
    extra = sys.argv[2:] or ["", "", "", "0"]
    preview(sys.argv[1], {"title": extra[0], "from": extra[1], "to": extra[2], "km": extra[3]})
