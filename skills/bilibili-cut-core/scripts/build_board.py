#!/usr/bin/env python3
"""Inject board/analysis.json into the edit board HTML."""

import json
import sys
from pathlib import Path

TOKEN = "/*__ANALYSIS__*/"
REQUIRED = ("board_id", "style", "route", "date", "title", "spine", "approach", "beats", "clips", "covers")
CLIP_FIELDS = ("id", "file", "kind", "duration", "thumb", "speech", "subtitle", "keep", "beat", "in_sec", "out_sec")


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: build_board.py <footage-dir>")
    root = Path(sys.argv[1]).expanduser().resolve()
    analysis_path = root / "board" / "analysis.json"
    if not analysis_path.exists():
        sys.exit(f"缺少 {analysis_path}")
    data = json.loads(analysis_path.read_text())
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        sys.exit("analysis.json 缺少: " + ", ".join(missing))
    if data["style"] not in ("walk", "scenic"):
        sys.exit("style 只能是 walk（边走边说）或 scenic（风景旁白）")
    if not data["clips"]:
        sys.exit("clips 是空的")
    for option in data.get("music_options") or []:
        if not (root / option.get("file", "")).exists():
            sys.exit(f"配乐候选不在: {option.get('file')}")
    for key in ("map_samples",):
        for src in data.get(key) or []:
            if not (root / src).exists():
                sys.exit(f"{key} 里的图不在: {src}")
    if not data["covers"]:
        sys.exit("至少给一张封面")
    for clip in data["clips"]:
        absent = [key for key in CLIP_FIELDS if key not in clip]
        if absent:
            sys.exit(f"{clip.get('id', '?')} 缺少: {', '.join(absent)}")
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (Path(__file__).resolve().parent.parent / "board" / "template.html").read_text()
    if TOKEN not in template:
        sys.exit("模板里没有分析占位")
    html = template.replace(TOKEN, "window.ANALYSIS = " + payload + ";", 1)
    dest = root / "剪辑方案.html"
    dest.write_text(html)
    print(dest)


if __name__ == "__main__":
    main()
