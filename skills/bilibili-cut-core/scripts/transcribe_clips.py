#!/usr/bin/env python3
"""Fill inventory speech, audio event, and voiced spans. Run with the whisper-tiny env python."""

import json
import re
import subprocess
import sys
from pathlib import Path

TAG = re.compile(r"<\|[^|]*\|>")
VOICE_BAND = "highpass=f=200,lowpass=f=3500"
SILENCE_BELOW_MEAN = 4.0
SILENCE_MIN = 0.45


def clean(text):
    text = TAG.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def voiced_spans(wav, duration):
    """Wind and footsteps sit mostly outside the voice band, so detect silence there,
    relative to each clip's own level."""
    probe = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(wav), "-af", f"{VOICE_BAND},volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    mean = re.search(r"mean_volume: (-?[\d.]+)", probe.stderr)
    threshold = max(-50.0, min(-20.0, float(mean.group(1)) - SILENCE_BELOW_MEAN)) if mean else -32.0
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", str(wav), "-af", f"{VOICE_BAND},silencedetect=noise={threshold:.1f}dB:d={SILENCE_MIN}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    spans = []
    cursor = 0.0
    for line in proc.stderr.splitlines():
        start = re.search(r"silence_start: ([\d.]+)", line)
        end = re.search(r"silence_end: ([\d.]+)", line)
        if start:
            begin = float(start.group(1))
            if begin - cursor > 0.25:
                spans.append([round(cursor, 2), round(begin, 2)])
        if end:
            cursor = float(end.group(1))
    if duration - cursor > 0.25:
        spans.append([round(cursor, 2), round(duration, 2)])
    return spans


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: transcribe_clips.py <footage-dir>")
    root = Path(sys.argv[1]).expanduser().resolve()
    inventory_path = root / "board" / "inventory.json"
    if not inventory_path.exists():
        sys.exit("先跑 probe_clips.py")
    try:
        from mlx_audio.stt.utils import load_model
    except ImportError:
        sys.exit("当前 Python 没有 mlx-audio。把可用解释器写进 studio/local.json 的 python")

    data = json.loads(inventory_path.read_text())
    pending = [
        clip for clip in data["clips"]
        if clip.get("kind") == "video" and clip.get("wav") and "audio_event" not in clip
    ]
    if not pending:
        print("没有需要转写的片段")
        return
    print(f"loading SenseVoice, {len(pending)} clips", flush=True)
    model = load_model("mlx-community/SenseVoiceSmall")
    for clip in pending:
        wav = root / clip["wav"]
        out = model.generate(str(wav), language="zh", use_itn=True)
        text = clean(getattr(out, "text", "") or "")
        segments = getattr(out, "segments", None) or [{}]
        event = segments[0].get("event") or ""
        clip["speech"] = text
        clip["audio_event"] = event
        clip["voiced"] = voiced_spans(wav, float(clip.get("duration") or 0)) if text else []
        if clip["voiced"]:
            clip["speech_start"] = clip["voiced"][0][0]
            clip["speech_end"] = clip["voiced"][-1][1]
        mark = " [BGM，多半是车里的歌，不算口播]" if event == "BGM" else ""
        print(f"{clip['id']} {text}{mark}", flush=True)
        inventory_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("DONE", inventory_path)


if __name__ == "__main__":
    main()
