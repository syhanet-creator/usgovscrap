#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.bat/run.sh에서 호출하는 통합 실행 스크립트.
패키지 설치 → 스크랩+번역 실행 → 로컬 웹서버 시작을 순서대로 수행합니다.
"""

import subprocess
import sys


def pip_install():
    base = [
        sys.executable, "-m", "pip", "install", "--quiet",
        "--disable-pip-version-check",
        "requests", "beautifulsoup4", "lxml", "deep-translator",
    ]
    result = subprocess.run(base)
    if result.returncode != 0:
        subprocess.run(base + ["--break-system-packages"], check=True)


def main():
    print("=" * 50)
    print(" 미국 중앙부처 보도자료 스크랩 + 한글 번역 실행")
    print("=" * 50)
    print()

    print("[1/2] 필요한 패키지 확인/설치 중...")
    pip_install()

    print("[2/2] 스크랩 + 번역 실행 중... (기관 수가 많아 1~3분 소요될 수 있습니다)")
    subprocess.run([sys.executable, "scrape.py"], check=True)

    print()
    import serve
    serve.main("index.html")


if __name__ == "__main__":
    main()
