"""
마인크래프트 서버 관리 봇 - 메인 실행 파일
"""

import discord
from discord.ext import commands
import signal
import sys

# 설정 파일 import
from config import (
    TOKEN,
    BOT_OWNER_ID,
    BASE_PATH,
    SERVERS_DIR,
    AUTO_SCAN_SERVERS,
    MINECRAFT_SERVERS,
    DEFAULT_TERMINAL_MODE,
    DEFAULT_MIN_MEMORY,
    DEFAULT_MAX_MEMORY,
    RCON_AUTO_PASSWORD,
    RCON_DEFAULT_PORT,
    REQUIRED_PERMISSION
)

# 유틸리티 함수 import
from utils import is_authorized

# 마인크래프트 모듈 import
from modules.minecraft import (
    ServerManager,
    ServerScanner,
    ServerConfigurator,
    setup_commands as setup_mc_commands
)


class MinecraftBot(commands.Bot):
    """마인크래프트 서버 관리 봇 클래스"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        # 서버 설정 준비
        servers_config = self._prepare_servers()
        
        # 서버 매니저 초기화
        self.mc = ServerManager(
            bot=self,
            base_path=str(BASE_PATH),
            servers_config=servers_config,
            default_server=self._get_default_server(servers_config)
        )
        
        # 종료 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def _prepare_servers(self) -> dict:
        """서버 설정 준비 (자동 스캔 또는 수동 설정)"""
        if AUTO_SCAN_SERVERS:
            print("\n🔍 자동 서버 스캔 모드")
            
            # Configurator 초기화
            configurator = ServerConfigurator(
                default_min_memory=DEFAULT_MIN_MEMORY,
                default_max_memory=DEFAULT_MAX_MEMORY
            )
            
            # Scanner 초기화 및 스캔
            scanner = ServerScanner(SERVERS_DIR, configurator)
            servers = scanner.scan_all_servers()
            
            # 스캔 결과 출력
            print(scanner.get_server_summary(servers))
            
            # 터미널 모드 설정
            for server_id, config in servers.items():
                if 'terminal_mode' not in config:
                    config['terminal_mode'] = DEFAULT_TERMINAL_MODE
            
            return servers
        else:
            print("\n⚙️ 수동 서버 설정 모드")
            return MINECRAFT_SERVERS.copy()
    
    def _get_default_server(self, servers_config: dict) -> str:
        """기본 서버 ID 결정"""
        if not servers_config:
            return "main"
        
        # 첫 번째 서버를 기본으로
        return list(servers_config.keys())[0]
    
    def is_authorized(self, user: discord.User, required_permission: str = None) -> bool:
        """권한 확인"""
        if required_permission is None:
            required_permission = REQUIRED_PERMISSION
        return is_authorized(user, required_permission)
    
    def signal_handler(self, signum, frame):
        """종료 시그널 처리"""
        print("\n\n⚠️ 종료 시그널 수신...")
        import asyncio
        asyncio.create_task(self.cleanup_and_exit())
    
    async def cleanup_and_exit(self):
        """정리 작업 후 종료"""
        try:
            await self.mc.cleanup_on_shutdown()
        except Exception as e:
            print(f"정리 중 오류: {e}")
        finally:
            await self.close()
            sys.exit(0)
    
    async def setup_hook(self):
        """봇 시작 시 슬래시 명령어 등록 및 동기화"""
        # 명령어 등록
        setup_mc_commands(self)
        
        # 명령어 동기화
        await self.tree.sync()
        print("✅ 슬래시 명령어 동기화 완료!")
    
    async def on_ready(self):
        """봇 준비 완료"""
        print("\n" + "="*60)
        print(f"🤖 Logged on as {self.user}!")
        print("="*60)
        
        # 봇 소유자 정보
        try:
            owner = await self.fetch_user(BOT_OWNER_ID)
            print(f"👤 봇 소유자: {owner.name} (ID: {owner.id})")
        except:
            print(f"⚠️ 경고: BOT_OWNER_ID({BOT_OWNER_ID})가 올바르지 않습니다!")
        
        # 상태 메시지
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game("마인크래프트 서버 관리 🎮")
        )
        
        # 서버 목록
        # 서버 목록 (main.py의 on_ready 메서드 내부)
        print(f"\n📋 관리 중인 서버: {len(self.mc.servers_config)}개")
        for server_id, config in self.mc.servers_config.items():
            status = "🟢" if self.mc.is_server_running(server_id) else "🔴"
            
            # 메모리 정보 안전하게 가져오기
            memory_config = config.get('memory', {})
            min_mem = memory_config.get('min', 'N/A')
            max_mem = memory_config.get('max', 'N/A')
            memory = f"{min_mem}-{max_mem}MB"
            
            print(f"   {status} [{server_id}] {config.get('name', server_id)} ({memory})")
        
        print("\n" + "="*60)
        print("🚀 봇이 준비되었습니다!")
        print("💡 Discord에서 /서버목록 을 입력하여 서버를 확인하세요")
        print("="*60 + "\n")
    
    async def on_error(self, event, *args, **kwargs):
        """에러 처리"""
        import traceback
        print(f"\n❌ 오류 발생 (이벤트: {event})")
        traceback.print_exc()
    
    async def close(self):
        """봇 종료"""
        print("\n👋 봇을 종료합니다...")
        await self.mc.cleanup_on_shutdown()
        await super().close()


def main():
    """봇 실행"""
    try:
        bot = MinecraftBot()
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("\n" + "="*60)
        print("❌ 로그인 실패: 봇 토큰이 올바르지 않습니다!")
        print("="*60)
        print("\n💡 해결 방법:")
        print("1. config.py 파일을 열어주세요")
        print("2. TOKEN 값이 올바른지 확인하세요")
        print("3. Discord Developer Portal에서 새 토큰을 발급받으세요")
        print("   https://discord.com/developers/applications")
        print("="*60 + "\n")
    except KeyboardInterrupt:
        print("\n👋 봇을 종료합니다...")
    except Exception as e:
        print("\n" + "="*60)
        print(f"❌ 예상치 못한 오류 발생: {e}")
        print("="*60 + "\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()