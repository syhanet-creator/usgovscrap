#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index.html을 file:// 로 직접 열면 브라우저가 보안 정책(CORS)상
로컬 data.json을 fetch()로 읽지 못합니다. 이를 피하기 위해
간단한 로컬 웹서버를 띄워 http://localhost 로 열어줍니다.
"""

import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

PORT = 8765


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def find_free_port(start=PORT):
    port = start
    while port < start + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start


def main(page=None):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = find_free_port()
    if page is None:
        page = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    url = f"http://127.0.0.1:{port}/{page}"

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"로컬 서버 시작: {url}")
        print("이 창을 닫거나 Ctrl+C를 누르면 웹앱이 종료됩니다.")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n서버를 종료합니다.")


if __name__ == "__main__":
    main()
