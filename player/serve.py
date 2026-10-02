#!/usr/bin/env python3
"""Serve the player with HTTP Range so Chrome can scrub/rewind MP3s.

python3 -m http.server ignores Range and returns the whole file as 200.
Chrome then refuses currentTime changes and the playhead snaps to 0:00.

Also saves listening feedback: POST /api/feedback/<slug> with the full JSON
list writes data/<slug>/feedback.json (read back as a normal static file).
"""

from __future__ import annotations

import argparse
import json
import re
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        rel = unquote(urlparse(path).path).lstrip("/")
        if not rel or rel.endswith("/"):
            rel = (rel or "") + "index.html"
        if any(part == ".." for part in Path(rel).parts):
            return str(ROOT / "__denied__")
        candidate = ROOT / rel
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            pass
        return str(ROOT / "__missing__")

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        self._send_file(path)

    def do_POST(self) -> None:
        m = re.fullmatch(r"/api/feedback/([a-z0-9-]+)", urlparse(self.path).path)
        perf_dir = ROOT / "data" / m.group(1) if m else None
        if not perf_dir or not (perf_dir / "performance.json").is_file():
            self.send_error(404, "Unknown performance")
            return
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            items = json.loads(body)
            if not isinstance(items, list):
                raise ValueError("expected a list")
            for it in items:
                if not (isinstance(it, dict) and isinstance(it.get("text"), str)
                        and float(it["start"]) <= float(it["end"])):
                    raise ValueError("each item needs start <= end and text")
        except (ValueError, KeyError, TypeError) as exc:
            self.send_error(400, f"Bad feedback: {exc}")
            return
        items.sort(key=lambda it: float(it["start"]))
        dest = perf_dir / "feedback.json"
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n")
        tmp.replace(dest)
        out = json.dumps({"saved": len(items)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_HEAD(self) -> None:
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        self._send_file(path, head_only=True)

    def _send_file(self, path: Path, head_only: bool = False) -> None:
        length = path.stat().st_size
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        range_h = self.headers.get("Range")
        start, end = 0, length - 1
        status = 200
        if range_h and range_h.startswith("bytes=") and length:
            spec = range_h.split("=", 1)[1].strip()
            if "," not in spec:
                a, _, b = spec.partition("-")
                try:
                    if a == "" and b:
                        suffix = int(b)
                        start = max(length - suffix, 0)
                    else:
                        start = int(a) if a else 0
                        end = int(b) if b else length - 1
                    start = max(0, min(start, length - 1))
                    end = max(start, min(end, length - 1))
                    status = 206
                except ValueError:
                    status = 200
                    start, end = 0, length - 1

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{length}")
            self.send_header("Content-Length", str(end - start + 1))
        else:
            self.send_header("Content-Length", str(length))
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--bind", default="127.0.0.1")
    args = p.parse_args()
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"Player: http://{args.bind}:{args.port}/")
    print("Chrome needs this server (not python -m http.server) to scrub/rewind.")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
