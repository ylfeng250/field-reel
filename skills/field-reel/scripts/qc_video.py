#!/usr/bin/env python3
"""Technical and editorial preflight for a finished Bilibili video."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 2.0
MAX_TRUE_PEAK = -1.0
MAX_AV_DRIFT = 0.5
COVER_SIZE = (1146, 716)
LINE_UNITS = 16
MAX_CPS = 9.0
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def run(cmd):
    return subprocess.run([str(part) for part in cmd], capture_output=True, text=True)


def ffprobe(path):
    proc = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1000:])
    return json.loads(proc.stdout or "{}")


def seconds(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def timecode(value):
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", value.strip())
    if not match:
        raise ValueError(value)
    hours, minutes, secs, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + secs + millis / (10 ** len(match.group(4)))


def units(text):
    return sum(0.5 if char.isascii() else 1.0 for char in text if not char.isspace())


def parse_srt(path):
    text = path.read_text(encoding="utf-8-sig")
    events = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        timing = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        start_text, end_text = [part.strip() for part in lines[timing].split("-->", 1)]
        events.append({
            "start": timecode(start_text),
            "end": timecode(end_text),
            "lines": lines[timing + 1:],
        })
    return events


def detector_pass(video):
    proc = run([
        "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", video,
        "-vf", "blackdetect=d=0.45:pic_th=0.98:pix_th=0.10,freezedetect=n=-50dB:d=1.0",
        "-af", "silencedetect=noise=-50dB:d=1.0,ebur128=peak=true",
        "-f", "null", "-",
    ])
    log = proc.stderr
    black = [
        {"start": float(a), "end": float(b), "duration": float(c)}
        for a, b, c in re.findall(
            r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", log
        )
    ]
    freeze_starts = [float(value) for value in re.findall(r"freeze_start:\s*([\d.]+)", log)]
    freeze_ends = [float(value) for value in re.findall(r"freeze_end:\s*([\d.]+)", log)]
    freeze_durations = [float(value) for value in re.findall(r"freeze_duration:\s*([\d.]+)", log)]
    freezes = []
    for index, start in enumerate(freeze_starts):
        duration = freeze_durations[index] if index < len(freeze_durations) else 0
        end = freeze_ends[index] if index < len(freeze_ends) else start + duration
        freezes.append({"start": start, "end": end, "duration": duration})
    silence_starts = [float(value) for value in re.findall(r"silence_start: ([\d.]+)", log)]
    silence_ends = [
        (float(end), float(duration))
        for end, duration in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", log)
    ]
    silences = []
    for index, start in enumerate(silence_starts):
        if index < len(silence_ends):
            end, duration = silence_ends[index]
            silences.append({"start": start, "end": end, "duration": duration})
    integrated = re.findall(r"\bI:\s*(-?[\d.]+) LUFS", log)
    peak = re.findall(r"\bPeak:\s*(-?[\d.]+) dBFS", log)
    return {
        "returncode": proc.returncode,
        "black": black,
        "freeze": freezes,
        "silence": silences,
        "integrated_lufs": float(integrated[-1]) if integrated else None,
        "true_peak_dbfs": float(peak[-1]) if peak else None,
        "errors": [
            line for line in log.splitlines()
            if re.search(r"\b(error|invalid|corrupt|failed)\b", line, re.I)
            and "Error string" not in line
        ][-20:],
    }


def extract_qc_frames(video, duration, output):
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("*.jpg"):
        old.unlink()
    stamps = sorted({max(0.0, duration * ratio) for ratio in (0.01, 0.2, 0.4, 0.6, 0.8, 0.98)})
    paths = []
    for index, stamp in enumerate(stamps, 1):
        dest = output / f"{index:02d}-{stamp:.1f}s.jpg"
        proc = run([
            "ffmpeg", "-y", "-nostdin", "-ss", f"{stamp:.3f}", "-i", video,
            "-frames:v", "1", "-vf", "scale=1280:-2", dest, "-loglevel", "error",
        ])
        if proc.returncode == 0:
            paths.append(str(dest))
    return paths


def music_license(decision):
    music = decision.get("music") or {}
    if not music.get("file"):
        return []
    issues = []
    registry_path = ROOT / "studio" / "rights" / "music.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    match = None
    wanted = Path(music["file"]).name.lower()
    for track in registry.get("tracks") or []:
        names = [Path(path).name.lower() for path in track.get("local_files") or []]
        if wanted in names:
            match = track
            break
    license_name = music.get("license") or (match or {}).get("license")
    credit = music.get("credit") or (match or {}).get("credit")
    if not license_name:
        issues.append(("warn", "配乐没有授权记录"))
    if license_name and "BY" in license_name.upper() and not credit:
        issues.append(("fail", f"{license_name} 配乐缺少署名"))
    return issues


def add(findings, level, code, message, evidence=None):
    findings.append({"level": level, "code": code, "message": message, "evidence": evidence})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--srt")
    parser.add_argument("--cover")
    parser.add_argument("--decision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        sys.exit(f"成片不存在: {video}")
    output = Path(args.output_dir).expanduser().resolve() if args.output_dir else video.parent
    output.mkdir(parents=True, exist_ok=True)
    findings = []

    try:
        probe = ffprobe(video)
    except RuntimeError as exc:
        sys.exit(f"ffprobe 失败: {exc}")
    fmt = probe.get("format") or {}
    duration = seconds(fmt.get("duration"))
    videos = [stream for stream in probe.get("streams") or [] if stream.get("codec_type") == "video"]
    audios = [stream for stream in probe.get("streams") or [] if stream.get("codec_type") == "audio"]
    if not videos:
        add(findings, "fail", "video_stream", "没有视频流")
    if not audios:
        add(findings, "fail", "audio_stream", "没有音频流")
    video_stream = videos[0] if videos else {}
    audio_stream = audios[0] if audios else {}
    width, height = int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)
    if width % 2 or height % 2:
        add(findings, "fail", "odd_dimensions", f"画面尺寸不是偶数：{width}×{height}")
    sample_rate = int(audio_stream.get("sample_rate") or 0)
    if audio_stream and sample_rate != 48000:
        add(findings, "fail", "sample_rate", f"音频采样率应为 48000 Hz，实际 {sample_rate}")
    video_duration = seconds(video_stream.get("duration")) or duration
    audio_duration = seconds(audio_stream.get("duration")) or duration
    drift = abs(video_duration - audio_duration)
    if audios and drift > MAX_AV_DRIFT:
        add(findings, "fail", "av_duration", f"音画时长相差 {drift:.3f} 秒")

    measured = detector_pass(video)
    if measured["returncode"] != 0 or measured["errors"]:
        add(findings, "fail", "decode", "完整解码出现错误", measured["errors"])
    loudness = measured["integrated_lufs"]
    true_peak = measured["true_peak_dbfs"]
    if loudness is None:
        add(findings, "fail", "loudness", "没有测到综合响度")
    elif abs(loudness - TARGET_LUFS) > LUFS_TOLERANCE:
        add(findings, "fail", "loudness", f"综合响度 {loudness:.1f} LUFS，目标 -14±2")
    if true_peak is None:
        add(findings, "warn", "true_peak", "没有测到真峰值")
    elif true_peak > MAX_TRUE_PEAK:
        add(findings, "fail", "true_peak", f"真峰值 {true_peak:.1f} dBFS，高于 -1 dBFS")

    ending = max(0.0, duration - 3.5)
    black_inside = [item for item in measured["black"] if item["start"] < ending]
    freeze_inside = [item for item in measured["freeze"] if item["start"] < ending and item["duration"] >= 1]
    silence_inside = [item for item in measured["silence"] if item["start"] < ending and item["duration"] >= 2]
    if black_inside:
        add(findings, "warn", "black", f"非结尾发现 {len(black_inside)} 段黑场", black_inside)
    if freeze_inside:
        add(findings, "warn", "freeze", f"非结尾发现 {len(freeze_inside)} 段定格", freeze_inside)
    if silence_inside:
        add(findings, "warn", "silence", f"非结尾发现 {len(silence_inside)} 段两秒以上静音", silence_inside)

    srt_path = Path(args.srt).expanduser().resolve() if args.srt else video.with_suffix(".srt")
    subtitle = {"path": str(srt_path), "events": 0, "issues": []}
    if not srt_path.exists():
        add(findings, "fail", "srt", f"找不到字幕文件：{srt_path}")
    else:
        try:
            events = parse_srt(srt_path)
        except (ValueError, UnicodeDecodeError) as exc:
            events = []
            add(findings, "fail", "srt_parse", f"字幕解析失败：{exc}")
        subtitle["events"] = len(events)
        previous_end = 0.0
        for index, event in enumerate(events, 1):
            issues = []
            if event["end"] <= event["start"]:
                issues.append("结束时间不晚于开始")
            if event["start"] < previous_end - 0.02:
                issues.append("和上一条重叠")
            if event["end"] > duration + 0.2:
                issues.append("超出成片时长")
            if len(event["lines"]) > 2:
                issues.append("超过两行")
            for line in event["lines"]:
                if units(line) > LINE_UNITS:
                    issues.append(f"单行 {units(line):.1f} 字")
            cue_units = units("".join(event["lines"]))
            cue_duration = max(0.01, event["end"] - event["start"])
            if cue_units / cue_duration > MAX_CPS:
                issues.append(f"阅读速度 {cue_units / cue_duration:.1f} 字/秒")
            if issues:
                subtitle["issues"].append({"index": index, "issues": issues, **event})
            previous_end = max(previous_end, event["end"])
        if subtitle["issues"]:
            add(findings, "fail", "subtitle", f"{len(subtitle['issues'])} 条字幕不合格", subtitle["issues"][:20])

    cover_path = Path(args.cover).expanduser().resolve() if args.cover else video.parent / "封面.jpg"
    cover = {"path": str(cover_path), "size": None}
    if not cover_path.exists():
        add(findings, "fail", "cover", f"找不到封面：{cover_path}")
    else:
        try:
            with Image.open(cover_path) as image:
                cover["size"] = list(image.size)
                if image.size != COVER_SIZE:
                    add(findings, "fail", "cover_size", f"封面应为 1146×716，实际 {image.width}×{image.height}")
        except OSError as exc:
            add(findings, "fail", "cover_decode", f"封面打不开：{exc}")

    decision_path = Path(args.decision).expanduser().resolve() if args.decision else video.parent / "edit-decision.json"
    decision = {}
    if decision_path.exists():
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        for level, message in music_license(decision):
            add(findings, level, "music_rights", message)
        if decision.get("voice_mode") == "clone":
            add(findings, "fail", "synthetic_voice", "项目已停用声音克隆，这份决策仍是 clone")
    else:
        add(findings, "warn", "decision", "没有 edit-decision.json，无法核对版权和剪辑决策")

    frames = extract_qc_frames(video, duration, output / "qc-frames")
    failures = [item for item in findings if item["level"] == "fail"]
    warnings = [item for item in findings if item["level"] == "warn"]
    result = {
        "version": 1,
        "status": "pass" if not failures else "fail",
        "video": {
            "path": str(video),
            "duration": duration,
            "width": width,
            "height": height,
            "video_codec": video_stream.get("codec_name"),
            "pixel_format": video_stream.get("pix_fmt"),
            "audio_codec": audio_stream.get("codec_name"),
            "sample_rate": sample_rate,
            "integrated_lufs": loudness,
            "true_peak_dbfs": true_peak,
            "av_duration_drift": round(drift, 3),
        },
        "cover": cover,
        "subtitle": subtitle,
        "detections": measured,
        "qc_frames": frames,
        "findings": findings,
        "manual_review": [
            "字幕没有挡脸、路牌、菜单和路线图",
            "地名、日期、公里、海拔、价格和营业时间有依据",
            "路人脸、车牌、门牌、二维码和私人屏幕已检查",
            "地图起终点和路线正确",
            "手机扬声器和耳机各听一次",
        ],
    }
    json_path = output / "qc-report.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 成片质检报告",
        "",
        f"结论：**{'通过机器检查' if not failures else '未通过'}**",
        "",
        f"- 成片：`{video.name}`",
        f"- 时长：{duration:.1f} 秒",
        f"- 画面：{width}×{height} / {video_stream.get('codec_name', '')}",
        f"- 音频：{audio_stream.get('codec_name', '')} / {sample_rate} Hz",
        f"- 响度：{loudness if loudness is not None else '—'} LUFS",
        f"- 真峰值：{true_peak if true_peak is not None else '—'} dBFS",
        f"- 音画时长差：{drift:.3f} 秒",
        "",
        "## 阻断项",
        "",
    ]
    lines += [f"- {item['message']}" for item in failures] or ["- 无"]
    lines += ["", "## 警告", ""]
    lines += [f"- {item['message']}" for item in warnings] or ["- 无"]
    lines += ["", "## 人工确认", ""]
    lines += [f"- [ ] {item}" for item in result["manual_review"]]
    lines += ["", f"抽帧：`{output / 'qc-frames'}`", ""]
    md_path = output / "质检报告.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    publish_path = output / "publish.json"
    if publish_path.exists():
        publish = json.loads(publish_path.read_text(encoding="utf-8"))
        publish["status"] = "qc_passed" if not failures else "qc_failed"
        publish["qc_report"] = md_path.name
        publish_path.write_text(json.dumps(publish, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json_path)
    print(md_path)
    print(f"{result['status']} failures={len(failures)} warnings={len(warnings)}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
