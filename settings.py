"""
봇 설정 로더
경로: settings.py

- 공통 기본값은 이 파일에, 토큰처럼 환경마다 다른 값은 profiles/<프로필>.py 에 둡니다.
  (profiles/*.py 는 git에 안 올라감, profiles/example.py 를 복사해서 사용)
- 진입 파일(run_prod.py / run_dev.py)이 activate()를 먼저 부른 다음 봇 모듈을 import 합니다.
  그래서 다른 모듈에서는 그냥 `from settings import TOKEN` 처럼 쓰면 됩니다.
- 프로필 파일에 여기 없는 이름을 쓰면 오타로 보고 시작을 멈춥니다.
"""

import importlib.util
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

# Linux: "screen" / Windows: "separate" (다음 단계에서 Windows 전용 실행 방식으로 교체 예정)
DEFAULT_TERMINAL_MODE = "screen" if OS_TYPE == "Linux" else "separate"

DEFAULT_MIN_MEMORY = 1024     # MB, 서버별 bot_config.json 없을 때 기본값
DEFAULT_MAX_MEMORY = 4096     # MB

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

    spec = importlib.util.spec_from_file_location(f"krangbot_profile_{profile}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    g = globals()
    unknown = []
    for key, value in vars(module).items():
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
    if problems:
        raise SystemExit(f"❌ {path.name} 설정 확인 필요:\n   - " + "\n   - ".join(problems))

    _ACTIVATED = True


def require_active():
    if not _ACTIVATED:
        raise SystemExit("❌ run_prod.py 또는 run_dev.py 로 실행해주세요. (프로필이 활성화되지 않았어요)")
