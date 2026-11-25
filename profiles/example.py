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

# ── 서버 프로세스 (필요할 때만 주석 풀어서 바꾸세요. 기본값과 설명은 settings.py) ──
# SERVER_CONSOLE_MODE = "minimized"       # "minimized" / "normal" / "hidden"
# JAVA_PATHS = {17: r"C:\Users\...\.jabba\jdk\temurin@17.0.19\bin\java.exe",
#               21: r"C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot\bin\java.exe"}
# STOP_TIMEOUT = 180                      # 정상 중지 대기 (초)
# AUTO_FORCE_KILL_ON_TIMEOUT = False      # 시간 초과 시 자동 강제 종료
# STOP_SERVERS_ON_BOT_EXIT = False        # 봇이 꺼질 때 서버도 끌지
# MEMORY_CHECK_ENABLED = True             # 시작 전 가용 RAM 검사
