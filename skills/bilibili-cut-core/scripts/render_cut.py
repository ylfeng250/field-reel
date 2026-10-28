#!/usr/bin/env python3
"""Render the edit decision: video, srt, cover, and 投稿.md.

    render_cut.py <footage-dir>            成片，要求页面已点「按这个剪」
    render_cut.py <footage-dir> --preview  720p 快速预览，草稿也能出
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import STYLES, field_level, needs_dub, voice_file

FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
YELLOW = (244, 227, 74)
MINT = (126, 232, 176)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

LINE_CHARS = 16
READ_CPS = 6.0
LOUDNESS = -14.0
TRUE_PEAK = -1.5
MAX_SLOW = 1.35
MUSIC_SOLO_LUFS = -16.0
MUSIC_UNDER_GAP = 9.0
DUCK_GAIN = 0.32
DUCK_RAMP = 0.35
VOICE_LEAD = 0.3
RENDER_VERSION = "2"
TRIM_PUNCT = "，。、；：,.;:"
BREAK_PUNCT = "，。！？；、,.!?;"


def run(cmd):
    proc = subprocess.run([str(part) for part in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or "")[-4000:])
        raise SystemExit(proc.returncode)
    return proc


def even(value):
    return max(2, int(round(value)) // 2 * 2)


def font(size):
    for index in (2, 1, 0):
        try:
            return ImageFont.truetype(FONT_PATH, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def probe_duration(path):
    proc = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(proc.stdout.strip())


def has_audio(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def units(text):
    return sum(0.5 if ch.isascii() else 1.0 for ch in text if not ch.isspace())


def index_at(line, limit):
    total = 0.0
    for index, ch in enumerate(line):
        total += 0.5 if ch.isascii() else 1.0
        if total > limit:
            return index
    return len(line)


def best_break(line, limit):
    hard = index_at(line, limit)
    for index in range(hard - 1, int(hard * 0.4), -1):
        if line[index] in BREAK_PUNCT:
            return index + 1
    return hard


def split_cues(text):
    cues = []
    for line in (text or "").splitlines():
        line = line.strip()
        while units(line) > LINE_CHARS * 2:
            cut = best_break(line, LINE_CHARS * 2)
            cues.append(line[:cut].strip())
            line = line[cut:].strip()
        if line:
            cues.append(line)
    return [cue.rstrip(TRIM_PUNCT) for cue in cues if cue.strip(TRIM_PUNCT)]


def wrap_two(text):
    if units(text) <= LINE_CHARS:
        return [text]
    cut = best_break(text, LINE_CHARS)
    left = text[:cut].rstrip(TRIM_PUNCT + " ")
    right = text[cut:].strip()
    if units(left) > LINE_CHARS or units(right) > LINE_CHARS:
        cut = index_at(text, LINE_CHARS)
        left = text[:cut].rstrip(TRIM_PUNCT + " ")
        right = text[cut:].strip()
    return [left, right]


def cue_png(text, width, height, dest):
    face = font(max(28, int(height * 0.042)))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    lines = wrap_two(text)
    draw = ImageDraw.Draw(image)
    gap = int(face.size * 0.28)
    heights = [face.getbbox(line)[3] - face.getbbox(line)[1] for line in lines]
    y = height - int(height * 0.08) - (sum(heights) + gap * (len(lines) - 1))
    stroke = max(2, int(face.size * 0.08))
    for line, line_height in zip(lines, heights):
        draw.text((width / 2, y), line, font=face, fill=WHITE, stroke_width=stroke, stroke_fill=BLACK, anchor="mt")
        y += line_height + gap
    image.save(dest)


def place(cues, spans):
    weights = [max(1.0, units(cue)) for cue in cues]
    total_weight = sum(weights)
    length = sum(end - start for start, end in spans)

    def at(pos):
        for start, end in spans:
            if pos < end - start - 1e-6:
                return start + pos
            pos -= end - start
        return spans[-1][1]

    edges = [0.0]
    for weight in weights:
        edges.append(edges[-1] + weight / total_weight * length)
    pauses = []
    run_len = 0.0
    for start, end in spans[:-1]:
        run_len += end - start
        pauses.append(run_len)
    for index in range(1, len(edges) - 1):
        if not pauses:
            break
        nearest = min(pauses, key=lambda pos: abs(pos - edges[index]))
        reach = 0.35 * min(edges[index] - edges[index - 1], edges[index + 1] - edges[index])
        if abs(nearest - edges[index]) <= reach:
            edges[index] = nearest

    timed = []
    for index, cue in enumerate(cues):
        begin = at(edges[index])
        finish = at(edges[index + 1] - 1e-3)
        timed.append([begin, finish, cue])
    for index, cue in enumerate(timed):
        cue[1] = max(cue[1], cue[0] + 0.8) + 0.25
        if index + 1 < len(timed):
            cue[1] = min(cue[1], timed[index + 1][0])
    return timed


def voiced_in(clip, inn, out):
    spans = []
    for start, end in clip.get("voiced") or []:
        start, end = max(start, inn), min(end, out)
        if end - start > 0.15:
            spans.append((start - inn, end - inn))
    return spans


def plan(root, clip, mode, level):
    photo = clip.get("kind") == "photo"
    inn = 0.0 if photo else float(clip.get("in_sec") or 0)
    out = float(clip.get("out_sec") or clip.get("duration") or 0)
    source_len = float(clip.get("duration") or out)
    if out - inn <= 0:
        sys.exit(f"{clip['file']} 出点不比进点晚")
    cues = split_cues(clip.get("subtitle") or "")
    dub = needs_dub(clip, level)
    voice = voice_file(root, clip) if dub and mode == "self" else None
    voice_len = probe_duration(voice) if voice else 0.0
    if voice:
        need = voice_len + VOICE_LEAD + 0.3
    elif dub and cues:
        need = sum(units(cue) for cue in cues) / READ_CPS + 0.5 * len(cues) + 0.6
    else:
        need = 0.0

    notes = []
    avail = out - inn
    if need > avail and not photo:
        longer = min(source_len, inn + need)
        if longer > out + 0.05:
            notes.append(f"出点 {out:.1f}→{longer:.1f}s")
            out = longer
            avail = out - inn
    slow = 1.0
    if photo:
        avail = max(avail, need)
    elif need > avail:
        slow = min(MAX_SLOW, need / avail)
        notes.append(f"放慢 {slow:.2f}×")
    shown = avail * slow
    pad = max(0.0, need - shown)
    if pad > 0.05:
        notes.append(f"末帧定格 {pad:.1f}s")
    else:
        pad = 0.0
    total = shown + pad

    speech = []
    if voice:
        speech = [(VOICE_LEAD, VOICE_LEAD + voice_len)]
        timed = place(cues, speech) if cues else []
    elif dub:
        timed = place(cues, [(0.3, max(0.6, total - 0.3))]) if cues else []
    elif cues:
        speech = voiced_in(clip, inn, out)
        timed = place(cues, speech or [(0.2, max(0.4, total - 0.2))])
    else:
        timed = []
    for cue in timed:
        cue[1] = min(cue[1], total)
    return {
        "clip": clip, "photo": photo, "inn": inn, "avail": avail, "slow": slow, "pad": pad,
        "total": total, "timed": timed, "voice": voice, "speech": speech, "notes": notes,
    }


def pick_size(decision, clips, preview):
    fixed = decision.get("resolution") or ""
    if "x" in fixed:
        width, height = (int(part) for part in fixed.lower().split("x"))
    else:
        tally = {}
        for clip in clips:
            if clip.get("kind") == "photo" or not clip.get("width"):
                continue
            key = (clip["width"], clip["height"])
            tally[key] = tally.get(key, 0) + float(clip.get("out_sec") or 0) - float(clip.get("in_sec") or 0)
        width, height = max(tally, key=tally.get) if tally else (1920, 1080)
    if preview:
        scale = 720 / min(width, height)
        width, height = width * scale, height * scale
    return even(width), even(height)


def map_settings(decision):
    cfg = dict(decision.get("map") or {})
    if decision.get("map_overlay"):
        cfg.setdefault("enabled", True)
    cfg.setdefault("title", decision.get("route") or "")
    return cfg


def render_segment(root, item, ctx, dest):
    clip = item["clip"]
    src = root / clip["file"]
    width, height = ctx["size"]
    total = item["total"]
    tmp = ctx["work"] / "layers"
    tmp.mkdir(exist_ok=True)
    stem = dest.stem

    cmd = ["ffmpeg", "-y", "-nostdin"]
    if item["photo"]:
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{total:.3f}", "-i", src]
    else:
        cmd += ["-ss", f"{item['inn']:.3f}", "-t", f"{item['avail']:.3f}", "-i", src]
    inputs = 1
    overlays = []
    for number, (begin, finish, text) in enumerate(item["timed"]):
        png = tmp / f"{stem}_{number:02d}.png"
        cue_png(text, width, height, png)
        cmd += ["-i", png]
        overlays.append((inputs, begin, finish))
        inputs += 1
    if item.get("map_point"):
        from route_map import card_layer
        point = item["map_point"]
        png = tmp / f"{stem}_map.png"
        card_layer(width, height, ctx["track"], point["lat"], point["lon"], point["clock"], ctx["map"]).save(png)
        cmd += ["-i", png]
        overlays.append((inputs, None, None))
        inputs += 1

    level = ctx["field"] * (0.18 if item["voice"] else 1.0)
    field_on = not item["photo"] and level > 0 and has_audio(src)
    if field_on:
        ambient = "0:a"
    else:
        cmd += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        ambient = f"{inputs}:a"
        inputs += 1
    if item["voice"]:
        cmd += ["-i", item["voice"]]
        voiced = f"{inputs}:a"
        inputs += 1

    vf = []
    if item["slow"] > 1.0:
        vf.append(f"setpts=PTS*{item['slow']:.4f}")
    vf.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p")
    if item["pad"]:
        vf.append(f"tpad=stop_mode=clone:stop_duration={item['pad']:.3f}")
    chain = ["[0:v]" + ",".join(vf) + "[v0]"]
    last = "v0"
    for number, (index, begin, finish) in enumerate(overlays, 1):
        enable = f":enable='between(t,{begin:.3f},{finish:.3f})'" if begin is not None else ""
        chain.append(f"[{last}][{index}:v]overlay=0:0:format=auto{enable}[v{number}]")
        last = f"v{number}"
    fade = min(0.34, max(0.16, total * 0.16)) if ctx["black"] else 0.0
    if fade:
        chain.append(f"[{last}]fade=t=in:st=0:d={fade:.3f}:color=black,fade=t=out:st={max(0.0, total - fade):.3f}:d={fade:.3f}:color=black[vout]")
    else:
        chain.append(f"[{last}]null[vout]")

    amb = []
    if field_on:
        amb.append("highpass=f=80")
        if item["slow"] > 1.0:
            amb.append(f"atempo={1 / item['slow']:.4f}")
        amb.append(f"volume={level:.3f}")
    amb += ["aformat=sample_rates=48000:channel_layouts=stereo", "apad", f"atrim=0:{total:.3f}", "asetpts=PTS-STARTPTS"]
    chain.append(f"[{ambient}]" + ",".join(amb) + ("[amb]" if item["voice"] else "[aout]"))
    if item["voice"]:
        delay = int(VOICE_LEAD * 1000)
        chain.append(f"[{voiced}]aformat=sample_rates=48000:channel_layouts=stereo,adelay={delay}:all=1,apad,atrim=0:{total:.3f}[vo]")
        chain.append("[amb][vo]amix=inputs=2:duration=first:normalize=0[aout]")

    cmd += [
        "-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "[aout]",
        *ctx["vcodec"], "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{total:.3f}", dest, "-loglevel", "error",
    ]
    run(cmd)


def segment_key(item, ctx):
    voice = item["voice"]
    payload = {
        "v": RENDER_VERSION,
        "file": item["clip"]["file"], "inn": round(item["inn"], 3), "avail": round(item["avail"], 3),
        "slow": round(item["slow"], 4), "pad": round(item["pad"], 3),
        "timed": [[round(a, 3), round(b, 3), t] for a, b, t in item["timed"]],
        "voice": [str(voice), voice.stat().st_mtime, voice.stat().st_size] if voice else None,
        "field": ctx["field"], "size": ctx["size"], "codec": ctx["vcodec"], "black": ctx["black"],
        "map": [item.get("map_point"), ctx["map"]] if item.get("map_point") else None,
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def loudness(path):
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(path), "-vn", "-af",
         f"loudnorm=I={LOUDNESS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not match:
        return None
    data = json.loads(match.group(0))
    return data if float(data["input_i"]) > -60 else None


def merge_spans(spans, gap=0.8):
    merged = []
    for start, end in sorted(spans):
        if merged and start - merged[-1][1] < gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def duck_expr(spans):
    r = DUCK_RAMP
    terms = [
        f"clip((t-{a - r:.3f})/{r},0,1)*clip(({b + r:.3f}-t)/{r},0,1)"
        for a, b in merge_spans(spans)
    ]
    return f"volume='1-{1 - DUCK_GAIN:.3f}*min(1,{'+'.join(terms)})':eval=frame"


def master(root, body, decision, speech, total, dest, work):
    music = decision.get("music") or {}
    music_file = root / music["file"] if music.get("file") else None
    if music_file and not music_file.exists():
        sys.exit(f"配乐文件不在: {music_file}")
    mix = work / "mix.wav"
    cmd = ["ffmpeg", "-y", "-nostdin", "-i", body]
    if music_file:
        body_level = loudness(body)
        music_level = loudness(music_file)
        if music_level is None:
            sys.exit("配乐是静音的？")
        if speech and body_level:
            target = float(body_level["input_i"]) - MUSIC_UNDER_GAP
        else:
            target = MUSIC_SOLO_LUFS
        target += float(music.get("volume_db") or 0)
        gain = target - float(music_level["input_i"])
        length = probe_duration(music_file)
        cross = min(3.0, length / 4)
        loops = max(1, math.ceil((total + 1) / max(1.0, length - cross)))
        for _ in range(loops):
            cmd += ["-i", music_file]
        parts = []
        prev = "1:a"
        for index in range(2, loops + 1):
            parts.append(f"[{prev}][{index}:a]acrossfade=d={cross:.2f}[m{index}]")
            prev = f"m{index}"
        fade_in = float(music.get("fade_in") or 1.6)
        fade_out = float(music.get("fade_out") or 3.0)
        bed = [
            f"atrim=0:{total:.3f}", "asetpts=PTS-STARTPTS",
            "aformat=sample_rates=48000:channel_layouts=stereo", f"volume={gain:.2f}dB",
        ]
        if speech:
            bed.append(duck_expr(speech))
        bed += [f"afade=t=in:d={fade_in:.2f}", f"afade=t=out:st={max(0.0, total - fade_out):.3f}:d={fade_out:.2f}"]
        parts.append(f"[{prev}]" + ",".join(bed) + "[bed]")
        parts.append("[0:a]aformat=sample_rates=48000:channel_layouts=stereo[main]")
        parts.append("[main][bed]amix=inputs=2:duration=first:normalize=0[mix]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "[mix]"]
        print(f"music {music_file.name} {gain:+.1f}dB loops {loops}", flush=True)
    else:
        cmd += ["-map", "0:a"]
    cmd += ["-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", mix, "-loglevel", "error"]
    run(cmd)

    measured = loudness(mix)
    audio = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    if measured:
        norm = (
            f"loudnorm=I={LOUDNESS}:TP={TRUE_PEAK}:LRA=11"
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true,aresample=48000"
        )
        audio = ["-af", norm] + audio
    run([
        "ffmpeg", "-y", "-nostdin", "-i", body, "-i", mix, "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", *audio, "-movflags", "+faststart", dest, "-loglevel", "error",
    ])
    return measured


def srt_time(seconds):
    ms = int(round(max(0, seconds) * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def clock_mmss(seconds):
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def safe_name(text):
    cleaned = "".join(ch for ch in text if ch not in '\\/:*?"<>|').strip()
    return cleaned or "路线"


def cover_crop(image, width, height):
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def draw_cover(image, top, bottom):
    image = cover_crop(image, 1146, 716)
    lines = [(text, face) for text, face in [(top, font(54)), (bottom, font(82))] if text]
    if not lines:
        return image
    draw = ImageDraw.Draw(image)
    gap = 12
    heights = [face.getbbox(text)[3] - face.getbbox(text)[1] for text, face in lines]
    y = image.height * 0.62 - (sum(heights) + gap * (len(lines) - 1)) / 2
    for (text, face), line_height in zip(lines, heights):
        draw.text(
            (image.width / 2, y), text, font=face, fill=YELLOW,
            stroke_width=max(6, int(face.size * 0.16)), stroke_fill=MINT, anchor="mt",
        )
        y += line_height + gap
    return image


def make_cover(root, decision, work):
    cover = decision.get("cover") or {}
    src = root / cover.get("file", "")
    if not cover.get("file") or not src.exists():
        sys.exit("封面文件不在")
    if cover.get("kind") == "video":
        frame = work / "cover_src.jpg"
        run(["ffmpeg", "-y", "-nostdin", "-ss", str(float(cover.get("time") or 0)), "-i", src, "-frames:v", "1", frame, "-loglevel", "error"])
        image = Image.open(frame)
    else:
        image = Image.open(src)
    poster = draw_cover(image, cover.get("caption_top") or "", cover.get("caption_bottom") or "")
    path = root / "封面.jpg"
    poster.save(path, quality=92)
    return path


def write_package(root, decision, chapters, out, srt, cover_path, total):
    description = (decision.get("description") or decision.get("spine") or "").strip()
    lines = [f"# {decision.get('title') or ''}", "", "## 简介", ""]
    if description:
        lines += [description, ""]
    if len(chapters) >= 2:
        lines += [f"{clock_mmss(at)} {label}" for at, label in chapters] + [""]
    credit = (decision.get("music") or {}).get("credit")
    if credit:
        lines += [credit.strip(), ""]
    tags = decision.get("tags") or []
    if tags:
        lines += ["## 标签", "", "、".join(tags), ""]
    lines += [
        "## 文件", "",
        f"- 成片：`{out.name}`（{clock_mmss(total)}）",
        f"- 封面：`{cover_path.name}`",
        f"- 字幕：`{srt.name}`。画面里已经烧了字幕，投稿时不要再传 CC 字幕，免得叠两层。",
    ]
    if len(chapters) >= 2:
        lines.append("- 章节：上面的时间点可以直接填进投稿页的「分段章节」。")
    path = root / "投稿.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    publish = {
        "version": 1,
        "status": "needs_qc",
        "title": decision.get("title") or "",
        "description": description,
        "tags": tags,
        "chapters": [{"time": round(at, 3), "label": label} for at, label in chapters],
        "video": out.name,
        "cover": cover_path.name,
        "subtitle": srt.name,
        "music": decision.get("music") or None,
        "bvid": "",
        "published_at": "",
    }
    publish_path = root / "publish.json"
    publish_path.write_text(json.dumps(publish, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, publish_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("footage")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    root = Path(args.footage).expanduser().resolve()
    decision_path = root / "edit-decision.json"
    if not decision_path.exists():
        sys.exit("还没有 edit-decision.json，页面上先存一下")
    decision = json.loads(decision_path.read_text())
    if not args.preview and not decision.get("confirmed"):
        sys.exit("页面还没点「按这个剪」。只想先看看节奏，用 --preview")
    style = decision.get("style") or "walk"
    if style not in STYLES:
        sys.exit("style 只能是 walk 或 scenic")

    clips = [clip for clip in decision.get("clips") or [] if clip.get("keep")]
    clips.sort(key=lambda clip: clip.get("order", 0))
    if not clips:
        sys.exit("没有留下的片段")
    missing = [clip["file"] for clip in clips if not (root / clip["file"]).exists()]
    if missing:
        sys.exit("找不到: " + ", ".join(missing))

    level = field_level(decision)
    mode = decision.get("voice_mode") or "field"
    if mode == "clone":
        sys.exit("声音克隆已停用。回方案页选择「只上字幕」或「我自己念」")
    if mode not in {"field", "self", "card"}:
        sys.exit("voice_mode 只能是 field、self、card")
    dubbed = [clip for clip in clips if needs_dub(clip, level)]
    if dubbed and mode == "field":
        sys.exit("这些段有旁白稿，页面上还没选旁白方式: " + ", ".join(clip["id"] for clip in dubbed))
    if mode == "self":
        absent = [clip["id"] for clip in dubbed if not voice_file(root, clip).exists()]
        if absent:
            sys.exit("你选了自己念。录音放到 board/voice/，文件名用片段编号: " + ", ".join(f"{item}.wav" for item in absent))

    work = root / "board" / "render"
    segs = work / ("segs-preview" if args.preview else "segs")
    segs.mkdir(parents=True, exist_ok=True)
    size = pick_size(decision, clips, args.preview)
    if args.preview:
        vcodec = ["-c:v", "libx264", "-crf", "27", "-preset", "veryfast"]
    elif size[0] >= 2560 or size[1] >= 2560:
        vcodec = ["-c:v", "libx265", "-crf", "20", "-preset", "medium", "-tag:v", "hvc1"]
    else:
        vcodec = ["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
    ctx = {
        "work": work, "size": size, "vcodec": vcodec, "field": level,
        "black": decision.get("transition") == "black" or bool(decision.get("black_fade")),
        "map": map_settings(decision), "track": None,
    }
    by_file = {}
    if ctx["map"].get("enabled"):
        from route_map import load_track
        ctx["track"] = load_track(root)
        if not ctx["track"]:
            sys.exit("要路线图，但这批素材没有定位")
        by_file = {point["file"]: point for point in ctx["track"]}

    used = set()
    items = []
    for index, clip in enumerate(clips, 1):
        item = plan(root, clip, mode, level)
        point = by_file.get(clip["file"])
        if point:
            item["map_point"] = {"lat": point["lat"], "lon": point["lon"], "clock": (clip.get("captured") or "")[11:16]}
        key = segment_key(item, ctx)
        dest = segs / f"{key}.mp4"
        used.add(dest.name)
        state = "cached" if dest.exists() else "render"
        print(f"{index:02d} {clip['id']} {item['total']:.1f}s {state} {' '.join(item['notes'])}".rstrip(), flush=True)
        if not dest.exists():
            partial = segs / f"{key}.part.mp4"
            render_segment(root, item, ctx, partial)
            partial.rename(dest)
        item["seg"] = dest
        item["length"] = probe_duration(dest)
        items.append(item)
    for old in segs.glob("*.mp4"):
        if old.name not in used:
            old.unlink()

    listing = work / "list.txt"
    listing.write_text("".join(f"file '{item['seg'].as_posix()}'\n" for item in items))
    body = work / "body.mp4"
    run(["ffmpeg", "-y", "-nostdin", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", body, "-loglevel", "error"])

    beats = {beat["id"]: beat.get("label") or "" for beat in decision.get("beats") or []}
    cursor = 0.0
    cues, speech, chapters = [], [], []
    for item in items:
        for begin, finish, text in item["timed"]:
            srt_text = "\n".join(wrap_two(text))
            cues.append(f"{len(cues) + 1}\n{srt_time(cursor + begin)} --> {srt_time(cursor + finish)}\n{srt_text}\n")
        speech += [(cursor + a, cursor + b) for a, b in item["speech"]]
        label = beats.get(item["clip"].get("beat") or "")
        if label and (not chapters or chapters[-1][1] != label):
            chapters.append((cursor, label))
        cursor += item["length"]

    if args.preview:
        out = work / "预览.mp4"
    else:
        day = (decision.get("date") or "").replace("-", "") or "未注明日期"
        out = root / f"{day}_{safe_name(decision.get('route') or '')}.mp4"
    measured = master(root, body, decision, speech, cursor, out, work)
    body.unlink()
    print(f"video {out}")
    print(f"duration {cursor:.1f}s {size[0]}x{size[1]}")
    if measured:
        print(f"loudness {measured['input_i']} LUFS -> {LOUDNESS}")
    if args.preview:
        return

    srt = out.with_suffix(".srt")
    srt.write_text("\n".join(cues), encoding="utf-8")
    cover_path = make_cover(root, decision, work)
    package, publish = write_package(root, decision, chapters, out, srt, cover_path, cursor)
    print(f"srt {srt}")
    print(f"cover {cover_path}")
    print(f"package {package}")
    print(f"publish {publish}")
    qc = Path(__file__).resolve().parents[2] / "field-reel" / "scripts" / "qc_video.py"
    if qc.exists():
        checked = subprocess.run([
            sys.executable, str(qc), str(out),
            "--srt", str(srt), "--cover", str(cover_path), "--decision", str(decision_path),
        ])
        if checked.returncode:
            sys.exit("成片已经生成，但质检没通过；先看质检报告，不标记为可投稿")


if __name__ == "__main__":
    main()
