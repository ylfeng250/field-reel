#!/usr/bin/env python3
"""读取哔哩哔哩公开空间数据，不需要登录。

用法见同目录《公开接口.md》。

    python3 bilibili_public.py
    python3 bilibili_public.py videos
    python3 bilibili_public.py seasons
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_mid():
    """账号 mid 只从环境变量或本地配置读取，不写进仓库。"""
    if os.environ.get("BILIBILI_MID"):
        return os.environ["BILIBILI_MID"].strip()
    config = Path(__file__).resolve().parent / "studio" / "local.json"
    if config.exists():
        data = json.loads(config.read_text(encoding="utf-8"))
        return str(data.get("bilibili_mid") or "").strip()
    return ""


MID = load_mid()
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
API = "https://api.bilibili.com"


def space_url(mid):
    return f"https://space.bilibili.com/{mid}"


def get(path, referer):
    """GET 一个返回 JSON 的公开接口。path 以 / 开头，或传完整 URL。"""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"HTTP {exc.code} {url} {body}") from exc
    if not raw.lstrip().startswith("{"):
        raise RuntimeError(f"接口返回了网页而不是 JSON，多半是被拦截：{url}")
    payload = json.loads(raw)
    code = payload.get("code")
    if code != 0:
        raise RuntimeError(f"{url} -> {code} {payload.get('message')}")
    return payload["data"]


def card(mid=MID):
    """昵称、签名、粉丝、关注、投稿数、获赞。"""
    return get(f"/x/web-interface/card?mid={mid}", space_url(mid))


def navnum(mid=MID):
    """空间各栏目数量：视频、合集、相簿等。"""
    return get(f"/x/space/navnum?mid={mid}", space_url(mid))


def videos(mid=MID, page_size=30):
    """全部投稿。默认按发布时间从新到旧。page_size 最大实测 50。"""
    if not 1 <= page_size <= 50:
        raise ValueError("page_size 只能是 1 到 50，再大接口返回 -400")
    found = []
    page_num = 1
    while True:
        query = urllib.parse.urlencode({"mid": mid, "pn": page_num, "ps": page_size})
        data = get(f"/x/space/arc/list?{query}", space_url(mid) + "/video")
        batch = data["archives"]
        found.extend(batch)
        total = data["page"]["count"]
        if not batch or page_num * data["page"]["ps"] >= total:
            return found
        page_num += 1
        time.sleep(0.3)


def seasons(mid=MID):
    """合集列表。每条只带最近几支预览，全量要用 season_videos。"""
    query = urllib.parse.urlencode({"mid": mid, "page_num": 1, "page_size": 20})
    data = get(f"/x/polymer/web-space/seasons_series_list?{query}", space_url(mid))
    return data["items_lists"]["seasons_list"]


def season_videos(mid, season_id, page_size=30):
    """一个合集里的全部稿件。"""
    found = []
    page_num = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "mid": mid,
                "season_id": season_id,
                "sort_reverse": "false",
                "page_num": page_num,
                "page_size": page_size,
            }
        )
        data = get(
            f"/x/polymer/web-space/seasons_archives_list?{query}",
            space_url(mid),
        )
        batch = data["archives"]
        found.extend(batch)
        page = data["page"]
        total = page["total"]
        if not batch or page_num * page["page_size"] >= total:
            return found
        page_num += 1
        time.sleep(0.3)


def tags(bvid):
    """视频标签。公开接口里这个比视频详情稳。"""
    data = get(
        f"/x/tag/archive/tags?bvid={urllib.parse.quote(bvid)}",
        f"https://www.bilibili.com/video/{bvid}",
    )
    return [item["tag_name"] for item in data]


def summary(mid=MID):
    profile = card(mid)
    info = profile["card"]
    rows = videos(mid)
    views = sorted(item["stat"]["view"] for item in rows)
    median = views[len(views) // 2] if views else 0
    return {
        "mid": info["mid"],
        "name": info["name"],
        "sign": info["sign"],
        "level": info["level_info"]["current_level"],
        "fans": info["fans"],
        "following": info["attention"],
        "videos": len(rows),
        "likes": profile["like_num"],
        "views": sum(views),
        "median_views": median,
        "latest": rows[0]["title"] if rows else "",
    }


def main(argv):
    if not MID:
        raise SystemExit("先在 studio/local.json 写 bilibili_mid，或设置环境变量 BILIBILI_MID")
    command = argv[1] if len(argv) > 1 else "summary"
    if command == "summary":
        info = summary()
        print(f"{info['name']}  mid {info['mid']}  Lv{info['level']}")
        print(info["sign"])
        print(
            f"粉丝 {info['fans']}  关注 {info['following']}  "
            f"投稿 {info['videos']}  获赞 {info['likes']}"
        )
        print(f"累计播放 {info['views']}  播放中位数 {info['median_views']}")
        print(f"最新：{info['latest']}")
        return
    if command == "videos":
        json.dump(videos(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    if command == "seasons":
        listing = []
        for item in seasons():
            meta = item["meta"]
            listing.append(
                {
                    "season_id": meta["season_id"],
                    "name": meta["name"],
                    "total": meta["total"],
                }
            )
        json.dump(listing, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    raise SystemExit("用法: python3 bilibili_public.py [summary|videos|seasons]")


if __name__ == "__main__":
    main(sys.argv)
