"""
실제 운영 봇 (본가 데스크톱, 친구들이 쓰는 봇)
경로: run_prod.py
설정: profiles/prod.py
"""

import sys

# Windows 에서 출력을 파일·파이프로 돌리면(서비스, 작업 스케줄러, 로그 리다이렉트) cp949 로 인코딩돼서
# 이모지 print 에서 UnicodeEncodeError 로 죽음 → UTF-8 로 고정
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import settings

settings.activate("prod")

from bot import main  # noqa: E402  (activate 다음에 import 해야 설정이 반영됨)

if __name__ == "__main__":
    main()
