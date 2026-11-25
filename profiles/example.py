"""
프로필 설정 템플릿
경로: profiles/example.py

이 파일을 복사해서 만드세요 (복사본은 git에 안 올라감):
  - profiles/prod.py : 본가 데스크톱, 친구들이 쓰는 실제 봇  → run_prod.py
  - profiles/dev.py  : 노트북 테스트 봇 (토큰 따로)           → run_dev.py

여기 없는 값은 settings.py 기본값을 씁니다.
settings.py 에 없는 이름을 쓰면 오타로 보고 시작할 때 멈춥니다.
"""

from pathlib import Path

# 디스코드 봇 토큰 — prod/dev 는 서로 다른 봇(토큰)을 쓰세요
TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

# 봇 소유자 디스코드 ID (최고 등급, 명령어로 바꿀 수 없음)
BOT_OWNER_ID = 0

# 마크 서버 폴더 (폴더 하나 = 서버 하나)
SERVERS_DIR = Path(r"C:\mcserver")

# dev 프로필 추천: 테스트용 디스코드 서버 ID → 명령어가 그 서버에만 즉시 반영
# prod 프로필: None (전역)
DEV_GUILD_ID = None

# 빈 서버 자동 종료 (RAM·CPU 확보용)
ENABLE_AUTO_SHUTDOWN = False
EMPTY_SERVER_TIMEOUT = 30
