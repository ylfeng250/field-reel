#!/usr/bin/env python3

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "bilibili-cut-core" / "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qc = load("qc_video", ROOT / "skills" / "field-reel" / "scripts" / "qc_video.py")
report = load("account_report", ROOT / "skills" / "field-reel" / "scripts" / "account_report.py")
audit = load("footage_audit", ROOT / "skills" / "bilibili-cut-core" / "scripts" / "footage_audit.py")
render = load("render_cut", ROOT / "skills" / "bilibili-cut-core" / "scripts" / "render_cut.py")


class TestStudioLogic(unittest.TestCase):
    def test_chinese_subtitle_units(self):
        self.assertEqual(qc.units("今天去山顶"), 5)
        self.assertEqual(qc.units("B站 4K"), 2.5)

    def test_parse_srt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.srt"
            path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n今天出发\n\n"
                "2\n00:00:03,100 --> 00:00:05,000\n往山顶走\n",
                encoding="utf-8",
            )
            events = qc.parse_srt(path)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["start"], 1)
            self.assertEqual(events[1]["lines"], ["往山顶走"])

    def test_pillar_classification(self):
        self.assertEqual(report.pillar("从山脚徒步上山"), "边走边说")
        self.assertEqual(report.pillar("沿公路看秋色"), "风景旁白")

    def test_hash_distance(self):
        self.assertEqual(audit.hamming("0000000000000000", "0000000000000000"), 0)
        self.assertEqual(audit.hamming("0000000000000000", "000000000000000f"), 4)

    def test_rendered_subtitle_lines_fit(self):
        cues = render.split_cues("这是一条刚好需要拆成两行而且不能超过十六个字的中文字幕")
        for cue in cues:
            lines = render.wrap_two(cue)
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(render.units(line) <= 16 for line in lines))


if __name__ == "__main__":
    unittest.main()
