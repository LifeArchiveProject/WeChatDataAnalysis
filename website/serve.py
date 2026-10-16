#!/usr/bin/env python3
"""官网本地预览服务器：禁用缓存，改完即所见。用法：python3 website/serve.py [port]"""
import functools
import http.server
import sys
from pathlib import Path


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path):
        # 和 GitHub Pages 一样：/changelog 这类不带后缀的地址，找不到同名文件或目录时回落到 changelog.html
        p = super().translate_path(path)
        if not Path(p).exists() and Path(p + ".html").is_file():
            return p + ".html"
        return p


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4321
    handler = functools.partial(NoCacheHandler, directory=str(Path(__file__).resolve().parent))
    http.server.test(HandlerClass=handler, port=port, bind="127.0.0.1")
