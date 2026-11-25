"""
봇 설정 로더
경로: settings.py

- 공통 기본값은 이 파일에, 토큰처럼 환경마다 다른 값은 profiles/<프로필>.py 에 둡니다.
  (profiles/*.py 는 git에 안 올라감, profiles/example.py 를 복사해서 사용)
- 진입 파일(run_prod.py / run_dev.py)이 activate()를 먼저 부른 다음 봇 모듈을 import 합니다.
  그래서 다른 모듈에서는 그냥 `from settings import TOKEN` 처럼 쓰면 됩니다.
- 프로필 파일에 여기 없는 이름을 쓰면 오타로 보고 시작을 멈춥니다.
"""

import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# ============================================
# 🌍 실행 환경 (자동)
# ============================================

PROFILE = None                 # activate() 후 "prod" / "dev"
OS_TYPE = platform.system()    # "Windows" / "Linux" / "Darwin"
SUPPORTED_OS = ("Windows", "Linux")

# ============================================
# 🔐 디스코드 (프로필에서 반드시 지정)
# ============================================

TOKEN = None
BOT_OWNER_ID = 0

# 지정하면 이 디스코드 서버(길드)에만 명령어 동기화 → 즉시 반영 (테스트 봇용)
# None 이면 전역 동기화 → 반영까지 시간이 걸릴 수 있음
DEV_GUILD_ID = None

# ============================================
# 📁 경로
# ============================================

BASE_PATH = PROJECT_ROOT                 # 구동기·플러그인·로그 등 봇 작업 폴더
SERVERS_DIR = PROJECT_ROOT / "servers"   # 마크 서버 폴더 (폴더 하나 = 서버 하나)
DATA_DIR = None                          # None 이면 data/<프로필> (권한 파일 등)

# ============================================
# 🎮 서버 스캔
# ============================================

AUTO_SCAN_SERVERS = True      # False 면 MINECRAFT_SERVERS 수동 설정 사용
MINECRAFT_SERVERS = {}

# Linux: "screen" / Windows: "process" (java 를 직접 실행하고 PID 파일로 추적)
DEFAULT_TERMINAL_MODE = "screen" if OS_TYPE == "Linux" else "process"

# 일반 jar 서버의 메모리 기본값 (bot_config.json 에 없을 때)
# Forge/NeoForge 서버팩은 user_jvm_args.txt 만 기준으로 쓰고 이 값은 안 씀
DEFAULT_MIN_MEMORY = 1024     # MB
DEFAULT_MAX_MEMORY = 4096     # MB

# ============================================
# 🖥️ 서버 프로세스 (terminal_mode="process", Windows 기본)
# ============================================

# 서버 콘솔 창: "minimized"(최소화된 창, 작업 표시줄에 보임) / "normal"(보이는 창) / "hidden"(창 없음)
# ⚠️ 콘솔 창을 X 로 닫으면 서버가 저장할 시간 없이 꺼질 수 있음 → 끌 때는 /서버중지
SERVER_CONSOLE_MODE = "minimized"

# 서버 폴더 안에 봇이 쓰는 상태 폴더 (PID 파일 process.json)
SERVER_STATE_DIRNAME = ".krangbot"

# Java 선택: 서버별 bot_config.json 의 "java" > JAVA_PATHS > 자동 감지 > DEFAULT_JAVA
# JAVA_PATHS 예: {17: r"C:\Program Files\Eclipse Adoptium\jdk-17...\bin\java.exe", 21: r"..."}
JAVA_PATHS = {}
JAVA_AUTO_DETECT = True       # Adoptium/Java/Microsoft/Zulu/BellSoft, ~/.jabba, ~/.jdks 에서 찾기
DEFAULT_JAVA = "java"         # 버전을 모르거나 못 찾았을 때 (PATH 의 java)

# 시작 직후 이 시간 안에 프로세스가 죽으면 "시작 실패"로 보고 (초)
START_CHECK_SECONDS = 15

# 정상 중지: RCON stop (RCON 이 안 되면 콘솔에 Ctrl+C) 후 이 시간까지 종료를 기다림 (초)
# 모드가 많은 팩은 저장이 오래 걸릴 수 있어서 넉넉하게
STOP_TIMEOUT = 180
# 위 시간이 지나도 안 꺼졌을 때 자동으로 강제 종료할지 (False: 알리기만 하고 둠 → /서버중지 강제)
AUTO_FORCE_KILL_ON_TIMEOUT = False
# 강제 중지: save-all flush → Ctrl+C → 이 시간 기다린 뒤에도 살아 있으면 프로세스 강제 종료 (초)
FORCE_STOP_GRACE = 30

# 봇이 꺼질 때 켜져 있는 서버도 같이 끌지 (False: 서버는 계속 돌고, 봇을 다시 켜면 재연결)
STOP_SERVERS_ON_BOT_EXIT = False

# 봇이 켜지 않은 서버(run.bat 으로 직접 켠 것 등)도 작업 폴더로 찾아서 "실행 중"으로 인식할지
ADOPT_EXTERNAL_SERVERS = True

# 시작 전 메모리 검사: 가용 RAM 이 (-Xmx + 여유분) 보다 적으면 시작 거부
MEMORY_CHECK_ENABLED = True
MEMORY_CHECK_BUFFER_MB = 1024

# RCON 응답 대기 시간 (초) — 서버가 멈췄을 때 봇이 같이 멈추지 않게
RCON_TIMEOUT = 5

# 봇 켤 때마다 구동기(Paper/Vanilla/Fabric/Forge + 플러그인) 업데이트 여부
# 재부팅이 잦은 데스크톱이라 기본은 끔 → 필요할 때 /구동기업데이트
UPDATE_CORES_ON_START = False

# ============================================
# ⏰ 빈 서버 자동 종료 (RAM·CPU 확보용)
# ============================================

ENABLE_AUTO_SHUTDOWN = False
EMPTY_SERVER_TIMEOUT = 30          # 분, 플레이어 0명 유지 시간
AUTO_SHUTDOWN_WARNING_TIME = 5     # 분, 종료 전 경고

# ============================================
# 로더
# ============================================

_ACTIVATED = False


def activate(profile: str):
    """profiles/<profile>.py 를 읽어 이 모듈의 값을 덮어씀. 봇 모듈 import 전에 호출."""
    global PROFILE, DATA_DIR, BASE_PATH, SERVERS_DIR, _ACTIVATED

    if _ACTIVATED:
        raise RuntimeError(f"settings 는 이미 '{PROFILE}' 프로필로 활성화됐어요.")

    if OS_TYPE not in SUPPORTED_OS:
        raise SystemExit(f"❌ 지원하지 않는 OS: {OS_TYPE} (지원: {', '.join(SUPPORTED_OS)})")

    path = PROJECT_ROOT / "profiles" / f"{profile}.py"
    if not path.exists():
        raise SystemExit(
            f"❌ 프로필 파일이 없어요: {path}\n"
            f"   profiles/example.py 를 profiles/{profile}.py 로 복사해서 값을 채워주세요."
        )

    # import 대신 소스를 직접 실행: .pyc 캐시를 안 만들고 안 읽음
    # (캐시를 쓰면 같은 초·같은 크기로 수정했을 때 옛 값이 로드될 수 있고, 토큰이 든 .pyc 가 남음)
    namespace = {"__file__": str(path), "__name__": f"krangbot_profile_{profile}"}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)

    g = globals()
    unknown = []
    for key, value in namespace.items():
        if not key.isupper():
            continue
        if key not in g or key.startswith("_") or key in ("PROFILE", "OS_TYPE", "SUPPORTED_OS", "PROJECT_ROOT"):
            unknown.append(key)
            continue
        g[key] = value
    if unknown:
        raise SystemExit(
            f"❌ {path.name} 에 알 수 없는(또는 바꿀 수 없는) 설정이 있어요: {', '.join(unknown)}\n"
            f"   오타인지 확인해주세요. 쓸 수 있는 설정은 settings.py 에 있습니다."
        )

    PROFILE = profile
    BASE_PATH = Path(BASE_PATH)
    SERVERS_DIR = Path(SERVERS_DIR)
    DATA_DIR = Path(DATA_DIR) if DATA_DIR else PROJECT_ROOT / "data" / profile

    problems = []
    if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        problems.append("TOKEN 이 비어 있어요")
    if not isinstance(BOT_OWNER_ID, int) or BOT_OWNER_ID <= 0:
        problems.append("BOT_OWNER_ID 가 비어 있어요 (/내아이디 로 확인 가능)")
    if DEV_GUILD_ID is not None and not isinstance(DEV_GUILD_ID, int):
        problems.append("DEV_GUILD_ID 는 숫자(int) 또는 None 이어야 해요")
    if SERVER_CONSOLE_MODE not in ("minimized", "normal", "hidden"):
        problems.append('SERVER_CONSOLE_MODE 는 "minimized" / "normal" / "hidden" 중 하나여야 해요')
    if not isinstance(JAVA_PATHS, dict):
        problems.append("JAVA_PATHS 는 {주버전: 경로} 형태의 dict 여야 해요")
    for _name in ("START_CHECK_SECONDS", "STOP_TIMEOUT", "FORCE_STOP_GRACE", "MEMORY_CHECK_BUFFER_MB", "RCON_TIMEOUT"):
        _v = globals()[_name]
        if not isinstance(_v, (int, float)) or _v < 0:
            problems.append(f"{_name} 는 0 이상의 숫자여야 해요")
    if problems:
        raise SystemExit(f"❌ {path.name} 설정 확인 필요:\n   - " + "\n   - ".join(problems))

    _ACTIVATED = True


def require_active():
    if not _ACTIVATED:
        raise SystemExit("❌ run_prod.py 또는 run_dev.py 로 실행해주세요. (프로필이 활성화되지 않았어요)")
