#!/usr/bin/env python3
"""Create a pre-shoot brief for one Bilibili episode."""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def slug(text):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", text, flags=re.UNICODE).strip("-")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", required=True, choices=("walk", "scenic"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--from", dest="start", default="")
    parser.add_argument("--to", dest="end", default="")
    parser.add_argument("--goal", default="")
    parser.add_argument("--output")
    args = parser.parse_args()

    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else ROOT / "studio" / "plans" / f"{args.date}-{slug(args.route)}.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"{output} 已存在，不覆盖")

    style_name = "边走边说" if args.style == "walk" else "风景旁白"
    route_line = f"{args.start} → {args.end}" if args.start or args.end else "待定"
    if args.style == "walk":
        anchors = [
            "入口/门头：",
            "路线或点单交代：",
            "关键决定/第一口：",
            "补给、价格或避坑：",
            "到达后的结论：",
        ]
    else:
        anchors = [
            "出发标志：",
            "第一种地貌/光线：",
            "中段明显变化：",
            "一个人的瞬间：",
            "到达和收尾：",
        ]
    lines = [
        f"# {args.date}｜{args.route}",
        "",
        f"- 风格：{style_name}",
        f"- 路线：{route_line}",
        f"- 这条片只讲：{args.goal or '待补一句主线'}",
        "- 观众看完能得到：",
        "- 需要核实的事实：",
        "",
        "## 五个锚点",
        "",
    ]
    lines += [f"- [ ] {item}" for item in anchors]
    lines += [
        "",
        "## 每个节点",
        "",
        "- [ ] 宽景 6–10 秒",
        "- [ ] 中景或移动",
        "- [ ] 路牌/脚步/食物等细节",
        "- [ ] 出发、转弯、上菜、到达等动作",
        "- [ ] 一句现场判断或真实反应",
        "- [ ] 10 秒纯环境声",
        "",
        "## 开机",
        "",
        "- [ ] 横屏后置主摄，镜头干净",
        "- [ ] 电量、容量、充电宝",
        "- [ ] 麦克风连接和防风",
        "- [ ] 原片不会经过微信转存",
        "- [ ] 路人脸、车牌、门牌和私人屏幕已留意",
        "",
        "## 封面",
        "",
        "- [ ] 至少拍一张主体清楚、横向、有留字空间的画面",
        "",
        "## 回来后",
        "",
        "- 素材目录：",
        "- 缺的镜头：",
        "- 实际发生但计划里没有的事：",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
