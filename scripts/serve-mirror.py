#!/usr/bin/env python3
"""Serve a mirrored publication the way its real origin serves it.

A plain `http.server` 404s on an unmatched path. The deployed origin behind
Cloudflare Pages does not: it answers every unmatched path with 200 and the
SPA's index.html. That difference is invisible for normal browsing, because the
viewer keeps all of its state in the query string on a single path, but it is
very visible to a reviewer who chases an advertised URL such as /sitemap.xml.

Reproducing the origin's behaviour keeps a comprehension sitting measuring the
product rather than measuring the mirror.

Usage: serve-mirror.py <port> <site-dir>
"""

import functools
import http.server
import socketserver
import sys
from pathlib import Path


class OriginFallbackHandler(http.server.SimpleHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        if code == 404:
            index = Path(self.directory) / "index.html"
            if index.is_file():
                body = index.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)

    def log_message(self, fmt, *args):  # keep the sitting's console quiet
        pass


def main() -> int:
    port = int(sys.argv[1])
    site = Path(sys.argv[2]).resolve()
    if not (site / "index.html").is_file():
        print(f"no index.html under {site}", file=sys.stderr)
        return 1
    handler = functools.partial(OriginFallbackHandler, directory=str(site))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving {site} on http://127.0.0.1:{port} (origin 404 fallback)")
        sys.stdout.flush()
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
