#!/usr/bin/env python3
"""Serve the edit board and save POST /api/decision to edit-decision.json."""

import json
import os
import sys
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: serve_board.py <footage-dir>")
    root = Path(sys.argv[1]).expanduser().resolve()
    board = root / "剪辑方案.html"
    if not board.exists():
        sys.exit(f"缺少 {board}，先跑 build_board.py")

    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.split("?", 1)[0] in ("/", ""):
                self.path = "/剪辑方案.html"
            return super().do_GET()

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/decision":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                self.send_error(400, "bad length")
                return
            try:
                data = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self.send_error(400, "bad json")
                return
            if not isinstance(data, dict) or "confirmed" not in data or "clips" not in data:
                self.send_error(400, "need confirmed and clips")
                return
            dest = root / "edit-decision.json"
            text = json.dumps(data, ensure_ascii=False, indent=2)
            history = root / "board" / "decisions"
            history.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
            state = "confirmed" if data.get("confirmed") else "draft"
            (history / f"{stamp}-{state}.json").write_text(text)
            dest.write_text(text)
            body = json.dumps({"ok": True, "path": str(dest)}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            state = "confirmed" if data.get("confirmed") else "draft"
            print(f"saved {state} -> {dest}", flush=True)

    handler = partial(Handler, directory=str(root))
    server = None
    port = 8765
    for port in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("8765-8775 都被占用了")
    url = f"http://127.0.0.1:{port}/"
    (root / "board").mkdir(exist_ok=True)
    (root / "board" / "server.txt").write_text(f"{url}\n{os.getpid()}\n")
    print(f"board {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stop")


if __name__ == "__main__":
    main()
