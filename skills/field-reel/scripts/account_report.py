#!/usr/bin/env python3
"""Build an account review from a public snapshot and optional creator metrics."""

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ANALYTICS = ROOT / "studio" / "analytics"

WALK_WORDS = (
    "徒步", "骑行", "骑车", "爬山", "路线", "探店", "牛肉面", "炒饭",
    "美食", "露营", "景区", "游玩", "逛", "登山", "步道",
)
SCENIC_WORDS = (
    "公路", "禾木", "喀纳斯", "风景", "秋日", "日落", "夜景", "雪",
    "草原", "河谷", "湖", "北境画廊",
)


def number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def pct(value):
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def pillar(title):
    walk = sum(word in title for word in WALK_WORDS)
    scenic = sum(word in title for word in SCENIC_WORDS)
    if walk > scenic:
        return "边走边说"
    if scenic > walk:
        return "风景旁白"
    return "其他/待标"


def median(values):
    return statistics.median(values) if values else 0


def load_private(path):
    if not path.exists():
        return {}
    found = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            bvid = (row.get("bvid") or "").strip()
            if bvid:
                found[bvid] = row
    return found


def row_stats(item, today):
    stat = item.get("stat") or {}
    published = datetime.fromtimestamp(number(item.get("pubdate")), tz=timezone.utc).astimezone()
    age = max(0, (today.date() - published.date()).days)
    views = number(stat.get("view"))
    engagement = sum(number(stat.get(key)) for key in ("like", "favorite", "reply", "share"))
    return {
        "bvid": item.get("bvid") or "",
        "title": item.get("title") or "",
        "published": published,
        "age": age,
        "duration": number(item.get("duration")),
        "views": views,
        "likes": number(stat.get("like")),
        "favorites": number(stat.get("favorite")),
        "replies": number(stat.get("reply")),
        "shares": number(stat.get("share")),
        "engagement_rate": engagement / views if views else 0,
        "pillar": pillar(item.get("title") or ""),
        "formatted": bool(re.match(r"^20\d{2}[.\-/]\d{1,2}", item.get("title") or "")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=str(ANALYTICS / "snapshots" / "latest.json"))
    parser.add_argument("--private", default=str(ANALYTICS / "creator-metrics.csv"))
    parser.add_argument("--output", default=str(ANALYTICS / "账号复盘.md"))
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot).expanduser().resolve()
    if not snapshot_path.exists():
        raise SystemExit("没有公开数据快照，先跑 account_snapshot.py")
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    today = datetime.now().astimezone()
    rows = [row_stats(item, today) for item in data.get("videos") or []]
    private = load_private(Path(args.private).expanduser().resolve())

    eligible = [row for row in rows if 7 <= row["age"] <= 180 and row["views"] > 0]
    base = median([row["views"] for row in eligible])
    for row in eligible:
        row["x_median"] = row["views"] / base if base else 0
    outliers = sorted(
        [row for row in eligible if row["x_median"] >= 2],
        key=lambda row: row["x_median"],
        reverse=True,
    )
    candidates = sorted(
        [row for row in eligible if 1.5 <= row["x_median"] < 2],
        key=lambda row: row["x_median"],
        reverse=True,
    )

    card = (data.get("profile") or {}).get("card") or {}
    profile = data.get("profile") or {}
    views = [row["views"] for row in rows]
    recent30 = [row for row in rows if row["age"] <= 30]
    recent90 = [row for row in rows if row["age"] <= 90]
    by_pillar = defaultdict(list)
    for row in eligible:
        by_pillar[row["pillar"]].append(row)

    lines = [
        "# B 站账号复盘",
        "",
        f"数据抓取：{data.get('fetched_at', '')}　报告生成：{today.isoformat(timespec='seconds')}",
        "",
        "## 公开数据基线",
        "",
        f"- 账号：{card.get('name', '')}（mid {data.get('mid', '')}）",
        f"- 粉丝：{number(card.get('fans')):,}",
        f"- 投稿：{len(rows)}",
        f"- 获赞：{number(profile.get('like_num')):,}",
        f"- 累计播放：{sum(views):,}",
        f"- 历史播放中位数：{median(views):,.0f}",
        f"- 最近 30 天：{len(recent30)} 条，中位播放 {median([r['views'] for r in recent30]):,.0f}",
        f"- 最近 90 天：{len(recent90)} 条，中位播放 {median([r['views'] for r in recent90]):,.0f}",
        "",
        "### 历史高播放（只用于找长期主题）",
        "",
    ]
    for row in sorted(rows, key=lambda item: item["views"], reverse=True)[:10]:
        lines.append(f"- {row['views']:,} · {row['published'].date()} · {row['title']}")
    lines += [
        "",
        "## 可比较窗口",
        "",
        f"只比较发布 7–180 天的 {len(eligible)} 条稿件；窗口中位数为 {base:,.0f}。新片未满 7 天不下结论。",
        "",
        "| 栏目（标题启发式） | 条数 | 中位播放 | 中位互动率 |",
        "|---|---:|---:|---:|",
    ]
    for name in ("边走边说", "风景旁白", "其他/待标"):
        group = by_pillar.get(name) or []
        lines.append(
            f"| {name} | {len(group)} | {median([r['views'] for r in group]):,.0f} | "
            f"{median([r['engagement_rate'] for r in group]) * 100:.1f}% |"
        )

    lines += ["", "## 自己的异常高表现", ""]
    if outliers:
        lines += [
            "| 倍数 | 播放 | 发布 | 标题 |",
            "|---:|---:|---|---|",
        ]
        for row in outliers[:15]:
            lines.append(
                f"| {row['x_median']:.1f}× | {row['views']:,} | "
                f"{row['published'].date()} | {row['title']} |"
            )
    else:
        lines.append("窗口内没有达到中位数 2 倍的稿件。")

    if candidates:
        lines += ["", "### 1.5–2 倍候选", ""]
        for row in candidates[:10]:
            lines.append(f"- {row['x_median']:.1f}× · {row['views']:,} · {row['title']}")

    lines += ["", "## 最新稿件（只观察，不急着判）", ""]
    for row in sorted(rows, key=lambda item: item["published"], reverse=True)[:10]:
        lines.append(
            f"- {row['published'].date()} · 第 {row['age']} 天 · {row['views']:,} 播放 · "
            f"{row['likes']} 赞 · {row['favorites']} 藏 · {row['title']}"
        )

    if private:
        lines += ["", "## 创作中心补充数据", ""]
        matched = [row for row in rows if row["bvid"] in private]
        if matched:
            lines += [
                "| 标题 | 曝光 | 点击率 | 平均观看 | 完播率 | 涨粉 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for row in matched[:20]:
                item = private[row["bvid"]]
                avg = item.get("avg_watch_seconds") or ""
                lines.append(
                    f"| {row['title']} | {item.get('impressions') or '—'} | "
                    f"{pct(item.get('click_rate'))} | {avg or '—'} 秒 | "
                    f"{pct(item.get('completion_rate'))} | {item.get('followers_gained') or '—'} |"
                )
        else:
            lines.append("CSV 里暂时没有能和公开稿件匹配的 bvid。")
    else:
        lines += [
            "",
            "## 创作中心数据缺口",
            "",
            "还没有填写曝光、点击率、平均观看、完播率和涨粉。公开 API 无法替代这些指标。",
        ]

    pattern_groups = defaultdict(list)
    for row in eligible:
        pattern_groups["日期开头" if row["formatted"] else "其他标题"].append(row)
    lines += [
        "",
        "## 包装观察",
        "",
        "| 标题形式 | 条数 | 中位播放 |",
        "|---|---:|---:|",
    ]
    for name, group in pattern_groups.items():
        lines.append(f"| {name} | {len(group)} | {median([r['views'] for r in group]):,.0f} |")
    lines += [
        "",
        "> 这是相关性，不是因果。发布时间、题材和账号阶段都不同；不要只凭这一行改标题体系。",
        "",
        "## 下轮复盘动作",
        "",
        "1. 给异常高稿件标注它解决了什么观众问题，而不只抄标题。",
        "2. 补最近主片的创作中心数据，先判断是点击问题还是留存问题。",
        "3. 在 `studio/experiments.md` 只登记一个下期要改变的变量。",
        "",
    ]

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    print(f"eligible {len(eligible)} median {base:.0f} outliers {len(outliers)}")


if __name__ == "__main__":
    main()
