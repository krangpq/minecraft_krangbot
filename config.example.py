"""
마인크래프트 서버 관리 봇 설정 파일 (템플릿)
경로: config.py

⚠️ 사용 방법:
1. 이 파일을 'config.py'로 복사하세요
2. TOKEN과 BOT_OWNER_ID를 본인의 정보로 변경하세요
3. servers/ 폴더에 마인크래프트 서버를 넣으세요
"""

from pathlib import Path
import platform

# ============================================
# 🔐 디스코드 봇 설정
# ============================================

# 디스코드 봇 토큰 (필수)
TOKEN = 'YOUR_DISCORD_BOT_TOKEN_HERE'

# 봇 소유자 디스코드 ID (필수)
BOT_OWNER_ID = 0

# ============================================
# 📁 경로 설정
# ============================================

# 프로젝트 루트 경로 (자동 설정)
PROJECT_ROOT = Path(__file__).parent
BASE_PATH = PROJECT_ROOT

# 서버 폴더 경로
SERVERS_DIR = BASE_PATH / 'servers'

# ============================================
# 🎮 마인크래프트 서버 자동 스캔 설정
# ============================================

# 운영체제 자동 감지
OS_TYPE = platform.system()  # 'Windows', 'Linux', 'Darwin'

# 서버 자동 스캔 사용 여부
# True: servers/ 폴더를 자동으로 스캔하여 서버 목록 생성
# False: MINECRAFT_SERVERS에 수동으로 설정
AUTO_SCAN_SERVERS = True

# ============================================
# 🖥️ 터미널 모드 설정
# ============================================

# 기본 터미널 모드 (AUTO_SCAN_SERVERS=True일 때 적용)
# Linux: "screen" (권장) 또는 "background"
# Windows: "separate" (개발용) 또는 "background"
# macOS: "separate" 또는 "background"
DEFAULT_TERMINAL_MODE = "screen" if OS_TYPE == "Linux" else "separate"

# ============================================
# 💾 메모리 설정 (기본값)
# ============================================

# 서버별 bot_config.json이 없을 때 사용되는 기본값
DEFAULT_MIN_MEMORY = 1024   # MB (최소 메모리)
DEFAULT_MAX_MEMORY = 4096   # MB (최대 메모리)

# ============================================
# 🔐 RCON 설정 (자동)
# ============================================

# RCON 비밀번호 자동 생성 (보안 강화)
# 서버 시작마다 새로운 비밀번호가 생성됩니다
RCON_AUTO_PASSWORD = True

# RCON 기본 포트 (서버별로 자동 할당)
RCON_DEFAULT_PORT = 25575

# ============================================
# ☁️ GCP 인스턴스 제어 설정 (선택사항)
# ============================================

# GCP 인스턴스 제어 사용 여부
ENABLE_GCP_CONTROL = False

# GCP 프로젝트 ID
GCP_PROJECT_ID = "your-project-id"

# GCP 서비스 계정 키 파일 경로 (JSON)
GCP_CREDENTIALS_FILE = BASE_PATH / "gcp-credentials.json"

# 관리할 인스턴스 정보
# {"인스턴스_이름": "zone"}
GCP_INSTANCES = {
    # 예시: 메인 마인크래프트 서버
    # "minecraft-main-server": "asia-northeast3-a",
}

# ============================================
# ⏰ 자동 종료 설정 (메인 서버용)
# ============================================

# 자동 종료 기능 활성화
# True: 플레이어가 없으면 자동으로 서버 종료
# False: 수동으로만 종료 가능
ENABLE_AUTO_SHUTDOWN = True

# 플레이어가 없을 때 대기 시간 (분)
# 예: 30 = 30분간 플레이어 없으면 자동 종료
# 추천: 30-60분 (너무 짧으면 잠깐 나간 플레이어가 불편)
EMPTY_SERVER_TIMEOUT = 30

# 자동 종료 전 경고 시간 (분)
# 예: 5 = 종료 5분 전에 로그 경고
AUTO_SHUTDOWN_WARNING_TIME = 5

# GCP 인스턴스 자동 중지 여부
# True: 모든 마인크래프트 서버 종료 시 인스턴스도 중지 (비용 절감!)
# False: 마인크래프트만 종료, 인스턴스는 유지
AUTO_STOP_INSTANCE = True

# 자동 중지할 인스턴스 정보 (AUTO_STOP_INSTANCE=True일 때 필요)
AUTO_SHUTDOWN_INSTANCE = {
    "project_id": "your-project-id",
    "name": "minecraft-main-server",
    "zone": "asia-northeast3-a"
}

# ============================================
# 📋 수동 서버 설정 (선택사항)
# ============================================

# AUTO_SCAN_SERVERS = False일 때만 사용
# 직접 서버를 설정하고 싶다면 아래 형식으로 추가

MINECRAFT_SERVERS = {
    # 예시: 수동으로 서버 추가
    # "custom_server": {
    #     "name": "커스텀 서버",
    #     "description": "수동 설정 서버",
    #     "path": "/path/to/server",
    #     "start_command": "java -Xmx4G -Xms2G -jar server.jar nogui",
    #     "stop_command": "stop",
    #     "port": 25565,
    #     "terminal_mode": "screen",
    #     "rcon": {
    #         "enabled": True,
    #         "host": "localhost",
    #         "port": 25575,
    #         "password": "password"
    #     }
    # }
}

# 기본 서버 (명령어에서 서버 지정 안 할 때 사용)
DEFAULT_SERVER = "main"

# ============================================
# 🛡️ 보안 설정
# ============================================

# 서버 제어 권한
REQUIRED_PERMISSION = "manage_guild"

# 명령어 실행 권한 (더 높은 권한)
COMMAND_EXECUTION_PERMISSION = "administrator"

# ============================================
# 📊 모니터링 설정
# ============================================

# 서버 상태 체크 주기 (초)
STATUS_CHECK_INTERVAL = 30

# 플레이어 활동 로그
LOG_PLAYER_ACTIVITY = True

# 성능 모니터링 (CPU, 메모리)
PERFORMANCE_MONITORING = True

# ============================================
# ⚙️ 고급 설정
# ============================================

# 서버 시작 대기 시간 (초)
SERVER_STARTUP_TIMEOUT = 300

# 서버 중지 대기 시간 (초)
SERVER_SHUTDOWN_TIMEOUT = 60

# 프로세스 강제 종료 사용 여부
FORCE_KILL_ON_TIMEOUT = True

# 로그 파일 최대 크기 (MB)
MAX_LOG_SIZE = 100

# 로그 파일 보관 기간 (일)
LOG_RETENTION_DAYS = 30

# 디버그 모드
DEBUG_MODE = False

# ============================================
# 💡 사용 가이드
# ============================================

"""
📁 서버 폴더 구조 예시:

servers/
├── survival/              # 서버 폴더명 = 서버 ID
│   ├── server.jar        # 필수
│   ├── bot_config.json   # 선택 (없으면 자동 생성)
│   ├── eula.txt          # 자동 처리
│   ├── server.properties # 자동 설정
│   └── world/
│
├── creative/
│   ├── server.jar
│   └── ...
│
└── modded/
    ├── forge.jar         # 모드 서버도 가능
    └── ...

📝 bot_config.json 형식 (선택사항):
{
  "memory": {
    "min": 2048,    # MB
    "max": 4096     # MB
  },
  "rcon": {
    "port": 25575,
    "auto_password": true
  },
  "description": "생존 서버"
}

⏰ 자동 종료 설정 예시:

# 30분 후 자동 종료 + 인스턴스 중지 (권장)
ENABLE_AUTO_SHUTDOWN = True
EMPTY_SERVER_TIMEOUT = 30
AUTO_STOP_INSTANCE = True

# 1시간 후 자동 종료 (여유롭게)
ENABLE_AUTO_SHUTDOWN = True
EMPTY_SERVER_TIMEOUT = 60
AUTO_STOP_INSTANCE = True

# 자동 종료 비활성화 (수동 관리)
ENABLE_AUTO_SHUTDOWN = False

# 마인크래프트만 종료, 인스턴스는 유지
ENABLE_AUTO_SHUTDOWN = True
AUTO_STOP_INSTANCE = False

💡 봇이 자동으로:
1. ✅ servers/ 폴더 스캔
2. ✅ bot_config.json 생성 (없으면)
3. ✅ EULA 동의 (자동)
4. ✅ RCON 설정 (비밀번호 자동 생성)
5. ✅ Screen 세션 생성 (Linux)
6. ✅ 서버 시작
7. ✅ 플레이어 없으면 자동 종료 (설정 시)
8. ✅ GCP 인스턴스 자동 중지 (설정 시)

🚀 사용 방법:
1. servers/ 폴더에 마인크래프트 서버 복사
2. config.py에서 자동 종료 설정
3. python main.py 실행
4. Discord에서 /서버시작
5. 플레이 후 방치 → 자동으로 종료 + 비용 절감!

☁️ GCP 인스턴스 제어 설정 방법:
1. GCP Console에서 서비스 계정 생성
   - 역할: Compute Engine 관리자
2. 서비스 계정 키 (JSON) 다운로드
3. 프로젝트 루트에 gcp-credentials.json으로 저장
4. config.py에서 AUTO_STOP_INSTANCE = True 설정
5. AUTO_SHUTDOWN_INSTANCE 정보 입력
"""

# ============================================
# 🔧 설정 검증
# ============================================

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 마인크래프트 서버 관리 봇 설정 확인")
    print("=" * 60)
    
    # 디스코드 설정
    print("\n📋 디스코드 설정:")
    if TOKEN == 'YOUR_DISCORD_BOT_TOKEN_HERE':
        print("❌ TOKEN이 설정되지 않았습니다!")
    else:
        print(f"✅ TOKEN: {TOKEN[:10]}...")
    
    if BOT_OWNER_ID == 0:
        print("❌ BOT_OWNER_ID가 설정되지 않았습니다!")
    else:
        print(f"✅ BOT_OWNER_ID: {BOT_OWNER_ID}")
    
    # 서버 스캔
    print(f"\n🎮 서버 설정:")
    print(f"자동 스캔: {'활성화' if AUTO_SCAN_SERVERS else '비활성화'}")
    print(f"서버 폴더: {SERVERS_DIR}")
    print(f"터미널 모드: {DEFAULT_TERMINAL_MODE}")
    
    if AUTO_SCAN_SERVERS and SERVERS_DIR.exists():
        server_folders = [f for f in SERVERS_DIR.iterdir() if f.is_dir() and not f.name.startswith('.')]
        print(f"\n발견된 서버 폴더: {len(server_folders)}개")
        for folder in server_folders:
            print(f"  - {folder.name}")
    
    # 메모리 설정
    print(f"\n💾 기본 메모리 설정:")
    print(f"최소: {DEFAULT_MIN_MEMORY}MB")
    print(f"최대: {DEFAULT_MAX_MEMORY}MB")
    
    # RCON
    print(f"\n🔐 RCON 설정:")
    print(f"자동 비밀번호: {'활성화' if RCON_AUTO_PASSWORD else '비활성화'}")
    
    # 자동 종료
    print(f"\n⏰ 자동 종료:")
    print(f"상태: {'활성화' if ENABLE_AUTO_SHUTDOWN else '비활성화'}")
    if ENABLE_AUTO_SHUTDOWN:
        print(f"대기 시간: {EMPTY_SERVER_TIMEOUT}분")
        print(f"경고 시간: {AUTO_SHUTDOWN_WARNING_TIME}분 전")
        print(f"인스턴스 중지: {'활성화' if AUTO_STOP_INSTANCE else '비활성화'}")
        if AUTO_STOP_INSTANCE:
            print(f"인스턴스: {AUTO_SHUTDOWN_INSTANCE.get('name', 'N/A')}")
    
    # GCP
    print(f"\n☁️ GCP 인스턴스 제어:")
    print(f"상태: {'활성화' if ENABLE_GCP_CONTROL else '비활성화'}")
    if ENABLE_GCP_CONTROL:
        print(f"프로젝트 ID: {GCP_PROJECT_ID}")
        print(f"관리 인스턴스: {len(GCP_INSTANCES)}개")
        if GCP_CREDENTIALS_FILE.exists():
            print(f"✅ 인증 파일 존재")
        else:
            print(f"❌ 인증 파일 없음: {GCP_CREDENTIALS_FILE}")
    
    print("\n" + "=" * 60)
    print("\n💡 설정 가이드:")
    print("1. TOKEN과 BOT_OWNER_ID 입력")
    print("2. servers/ 폴더에 마인크래프트 서버 복사")
    print("3. 자동 종료 설정 (ENABLE_AUTO_SHUTDOWN)")
    print("4. (선택) GCP 인스턴스 자동 중지 설정")
    print("5. python main.py 실행")
    print("=" * 60)

# ============================================
# 🔗 봇 간 통신 설정 (GCP 제어용)
# ============================================

# GCP 제어 기능 활성화 여부 (기본값 - 런타임에 변경됨)
ENABLE_GCP_CONTROL = False

# 제어 채널 ID (자동 설정됨)
CONTROL_CHANNEL_ID = None

# 컨트롤러 봇의 Discord ID (자동 설정됨)
CONTROLLER_BOT_ID = None

# GCP 인스턴스 이름
GCP_INSTANCE_NAME = "minecraft-main-server"