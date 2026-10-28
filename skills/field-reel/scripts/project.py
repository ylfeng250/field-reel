#!/usr/bin/env python3
"""Create and advance one video's project.json.

Examples:
  project.py init <dir> --style walk --date 2026-10-17 --route 山脚到山顶
  project.py status <dir> board
  project.py publish <dir> BVxxxx --at 2026-10-27T18:00:00+08:00
  project.py show <dir>
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

STATES = [
    "idea",
    "footage",
    "board",
    "confirmed",
    "preview",
    "final",
    "qc_passed",
    "ready",
    "published",
    "reviewed",
]


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_id(date, route):
    base = f"{date}-{route}".lower()
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", base, flags=re.UNICODE)
    return base.strip("-")


def path_for(folder):
    return Path(folder).expanduser().resolve() / "project.json"


def load(folder):
    path = path_for(folder)
    if not path.exists():
        sys.exit(f"没有 {path}，先运行 init")
    return path, json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_status(path, data, status, note=""):
    if status not in STATES:
        sys.exit("状态只能是: " + ", ".join(STATES))
    current = data.get("status") or "idea"
    if STATES.index(status) < STATES.index(current):
        sys.exit(f"不能从 {current} 倒退到 {status}；要返工就保留状态，在 notes 里记录")
    if status != current:
        data["status"] = status
        data.setdefault("status_history", []).append({"status": status, "at": now(), "note": note})
    data["updated_at"] = now()
    save(path, data)


def cmd_init(args):
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"素材目录不存在: {folder}")
    path = folder / "project.json"
    if path.exists() and not args.force:
        sys.exit(f"{path} 已存在；不覆盖。要重建请显式加 --force")
    created = now()
    data = {
        "version": 1,
        "id": clean_id(args.date, args.route),
        "style": args.style,
        "date": args.date,
        "route": args.route,
        "status": "footage",
        "created_at": created,
        "updated_at": created,
        "status_history": [{"status": "footage", "at": created, "note": "素材目录已建立"}],
        "deliverables": {
            "decision": "edit-decision.json",
            "cover": "封面.jpg",
            "package": "投稿.md",
            "qc": "质检报告.md",
        },
        "publication": {"bvid": "", "published_at": ""},
        "review": {"first_at": "", "month_at": "", "notes": ""},
        "facts_to_verify": [],
        "privacy_to_review": [],
        "notes": [],
    }
    save(path, data)
    print(path)


def cmd_status(args):
    path, data = load(args.folder)
    set_status(path, data, args.status, args.note)
    print(f"{data['id']} -> {data['status']}")


def cmd_publish(args):
    path, data = load(args.folder)
    data.setdefault("publication", {})["bvid"] = args.bvid
    data["publication"]["published_at"] = args.at or now()
    set_status(path, data, "published", "已记录 B 站稿件")
    print(f"{data['id']} published {args.bvid}")


def cmd_show(args):
    path, data = load(args.folder)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("folder")
    init.add_argument("--style", required=True, choices=("walk", "scenic"))
    init.add_argument("--date", required=True)
    init.add_argument("--route", required=True)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status")
    status.add_argument("folder")
    status.add_argument("status", choices=STATES)
    status.add_argument("--note", default="")
    status.set_defaults(func=cmd_status)

    publish = sub.add_parser("publish")
    publish.add_argument("folder")
    publish.add_argument("bvid")
    publish.add_argument("--at", default="")
    publish.set_defaults(func=cmd_publish)

    show = sub.add_parser("show")
    show.add_argument("folder")
    show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
