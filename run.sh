#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo " 미국 중앙부처 보도자료 스크랩 + 한글 번역 실행"
echo "============================================"
echo

if ! command -v python3 &> /dev/null; then
    echo "[오류] python3이 설치되어 있지 않습니다. https://www.python.org 에서 설치하세요."
    exit 1
fi

python3 run_all.py
