#!/usr/bin/env python3
"""Save a dated snapshot of the account's public Bilibili data."""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import bilibili_public  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mid", default=bilibili_public.MID)
    parser.add_argument("--output-dir", default=str(ROOT / "studio" / "analytics" / "snapshots"))
    args = parser.parse_args()

    stamped = datetime.now().astimezone()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = bilibili_public.card(args.mid)
    rows = bilibili_public.videos(args.mid)
    payload = {
        "version": 1,
        "fetched_at": stamped.isoformat(timespec="seconds"),
        "mid": str(args.mid),
        "profile": profile,
        "videos": rows,
        "limits": {
            "public": [
                "投稿时间",
                "播放",
                "点赞",
                "收藏",
                "评论",
                "弹幕",
                "分享",
            ],
            "not_public": [
                "曝光",
                "点击率",
                "平均观看时长",
                "完播率",
                "留存曲线",
                "涨粉来源",
            ],
        },
    }
    name = stamped.strftime("%Y-%m-%dT%H%M%S%z") + ".json"
    dest = out_dir / name
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(dest, out_dir / "latest.json")

    views = [int(item.get("stat", {}).get("view") or 0) for item in rows]
    views.sort()
    median = views[len(views) // 2] if views else 0
    card = profile.get("card") or {}
    print(f"{card.get('name')}  粉丝 {card.get('fans')}  投稿 {len(rows)}")
    print(f"累计播放 {sum(views)}  播放中位数 {median}")
    print(dest)


if __name__ == "__main__":
    main()
