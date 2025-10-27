"""
마인크래프트 서버 관리 봇 - 자동 종료 기능 포함
메인 서버에서 실행
"""

import discord
from discord.ext import commands, tasks
import signal
import sys
import os
import asyncio
from datetime import datetime

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
    REQUIRED_PERMISSION,
    # 자동 종료 설정
    ENABLE_AUTO_SHUTDOWN,
    EMPTY_SERVER_TIMEOUT,
    AUTO_SHUTDOWN_WARNING_TIME,
    AUTO_STOP_INSTANCE,
    AUTO_SHUTDOWN_INSTANCE,
    GCP_CREDENTIALS_FILE
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
        
        # GCP 인스턴스 제어 (자동 종료용)
        self.gcp = None
        if ENABLE_AUTO_SHUTDOWN and AUTO_STOP_INSTANCE:
            self._init_gcp_for_shutdown()
        
        # 자동 종료 상태 추적
        self.empty_since = {}  # {server_id: datetime}
        self.shutdown_notified = {}  # {server_id: bool}
        
        # 종료 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def _init_gcp_for_shutdown(self):
        """GCP 인스턴스 자동 중지를 위한 초기화"""
        try:
            if GCP_CREDENTIALS_FILE.exists():
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(GCP_CREDENTIALS_FILE)
            
            from google.cloud import compute_v1
            self.gcp_client = compute_v1.InstancesClient()
            self.gcp_project = AUTO_SHUTDOWN_INSTANCE.get('project_id')
            self.gcp_instance = AUTO_SHUTDOWN_INSTANCE.get('name')
            self.gcp_zone = AUTO_SHUTDOWN_INSTANCE.get('zone')
            
            if not all([self.gcp_project, self.gcp_instance, self.gcp_zone]):
                print("⚠️ AUTO_SHUTDOWN_INSTANCE 설정이 불완전합니다.")
                print("   config.py에서 project_id, name, zone을 모두 설정하세요.")
                self.gcp_client = None
                return
            
            print("✅ GCP 자동 중지 기능 활성화")
            print(f"   인스턴스: {self.gcp_instance}")
            
        except Exception as e:
            print(f"⚠️ GCP 자동 중지 초기화 실패: {e}")
            print("   자동 종료는 작동하지만 인스턴스는 수동으로 중지해야 합니다.")
            self.gcp_client = None
    
    def _prepare_servers(self) -> dict:
        """서버 설정 준비 (자동 스캔 또는 수동 설정)"""
        if AUTO_SCAN_SERVERS:
            print("\n🔍 자동 서버 스캔 모드")
            
            configurator = ServerConfigurator(
                default_min_memory=DEFAULT_MIN_MEMORY,
                default_max_memory=DEFAULT_MAX_MEMORY
            )
            
            scanner = ServerScanner(SERVERS_DIR, configurator)
            servers = scanner.scan_all_servers()
            
            print(scanner.get_server_summary(servers))
            
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
        return list(servers_config.keys())[0]
    
    def is_authorized(self, user: discord.User, required_permission: str = None) -> bool:
        """권한 확인"""
        if required_permission is None:
            required_permission = REQUIRED_PERMISSION
        return is_authorized(user, required_permission)
    
    def signal_handler(self, signum, frame):
        """종료 시그널 처리"""
        print("\n\n⚠️ 종료 시그널 수신...")
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
        setup_mc_commands(self)
        
        await self.tree.sync()
        print("✅ 슬래시 명령어 동기화 완료!")
        
        # 자동 종료 모니터링 시작
        if ENABLE_AUTO_SHUTDOWN:
            self.check_empty_servers.start()
            print(f"✅ 자동 종료 모니터링 시작 (대기 시간: {EMPTY_SERVER_TIMEOUT}분)")
    
    @tasks.loop(minutes=1)
    async def check_empty_servers(self):
        """서버 비어있는지 주기적으로 확인"""
        try:
            for server_id in self.mc.get_all_server_ids():
                # 서버 실행 중인지 확인
                if not self.mc.is_server_running(server_id):
                    # 서버가 꺼져있으면 초기화
                    if server_id in self.empty_since:
                        del self.empty_since[server_id]
                    if server_id in self.shutdown_notified:
                        del self.shutdown_notified[server_id]
                    continue
                
                # 서버 상태 조회
                status = await self.mc.get_server_status(server_id)
                
                if not status or not status.get('online'):
                    continue
                
                players = status.get('players', {})
                player_count = players.get('online', 0)
                
                if player_count == 0:
                    # 플레이어 없음
                    if server_id not in self.empty_since:
                        # 처음 비었음
                        self.empty_since[server_id] = datetime.now()
                        self.shutdown_notified[server_id] = False
                        print(f"⏰ [{server_id}] 서버가 비었습니다. {EMPTY_SERVER_TIMEOUT}분 후 자동 종료 예정")
                    else:
                        # 비어있던 시간 계산
                        elapsed = (datetime.now() - self.empty_since[server_id]).total_seconds() / 60
                        remaining = EMPTY_SERVER_TIMEOUT - elapsed
                        
                        # 경고 시간 전 알림
                        if remaining <= AUTO_SHUTDOWN_WARNING_TIME and not self.shutdown_notified.get(server_id, False):
                            print(f"⚠️ [{server_id}] {AUTO_SHUTDOWN_WARNING_TIME}분 후 자동 종료됩니다")
                            self.shutdown_notified[server_id] = True
                        
                        # 시간 초과 시 종료
                        if elapsed >= EMPTY_SERVER_TIMEOUT:
                            print(f"🛑 [{server_id}] {EMPTY_SERVER_TIMEOUT}분간 비어있어 자동 종료합니다")
                            await self.auto_shutdown_server(server_id)
                else:
                    # 플레이어 있음 - 초기화
                    if server_id in self.empty_since:
                        print(f"✅ [{server_id}] 플레이어 접속으로 자동 종료 취소")
                        del self.empty_since[server_id]
                    if server_id in self.shutdown_notified:
                        del self.shutdown_notified[server_id]
        
        except Exception as e:
            print(f"⚠️ 자동 종료 체크 오류: {e}")
    
    async def auto_shutdown_server(self, server_id: str):
        """서버 자동 종료 및 인스턴스 중지"""
        try:
            config = self.mc.get_server_config(server_id)
            
            print(f"📦 [{server_id}] 월드 저장 중...")
            # RCON으로 저장 시도
            if self.mc.has_rcon(server_id):
                await self.mc.send_command(server_id, "save-all")
                await asyncio.sleep(5)
            
            print(f"🛑 [{server_id}] 마인크래프트 서버 중지 중...")
            success, message = await self.mc.stop_server(server_id, force=False)
            
            if success:
                print(f"✅ [{server_id}] 서버 중지 완료")
                
                # GCP 인스턴스 자동 중지
                if AUTO_STOP_INSTANCE and hasattr(self, 'gcp_client') and self.gcp_client:
                    # 모든 마인크래프트 서버가 중지되었는지 확인
                    all_stopped = True
                    for sid in self.mc.get_all_server_ids():
                        if self.mc.is_server_running(sid):
                            all_stopped = False
                            break
                    
                    if all_stopped:
                        print(f"☁️ 모든 서버가 중지되어 GCP 인스턴스를 중지합니다...")
                        await self.stop_gcp_instance()
                    else:
                        print(f"ℹ️ 다른 서버가 실행 중이므로 인스턴스는 유지합니다")
            else:
                print(f"❌ [{server_id}] 서버 중지 실패: {message}")
            
            # 상태 초기화
            if server_id in self.empty_since:
                del self.empty_since[server_id]
            if server_id in self.shutdown_notified:
                del self.shutdown_notified[server_id]
        
        except Exception as e:
            print(f"❌ 자동 종료 오류: {e}")
    
    async def stop_gcp_instance(self):
        """GCP 인스턴스 중지"""
        try:
            print(f"⏳ GCP 인스턴스 중지 중: {self.gcp_instance}")
            
            await asyncio.to_thread(
                self.gcp_client.stop,
                project=self.gcp_project,
                zone=self.gcp_zone,
                instance=self.gcp_instance
            )
            
            print(f"✅ GCP 인스턴스 중지 요청 완료")
            print(f"💰 컴퓨팅 비용 절감 시작!")
            
        except Exception as e:
            print(f"❌ GCP 인스턴스 중지 실패: {e}")
            print(f"💡 Discord에서 /인스턴스중지 명령어를 사용하세요")
    
    async def on_ready(self):
        """봇 준비 완료"""
        print("\n" + "="*60)
        print(f"🤖 Logged on as {self.user}!")
        print("="*60)
        
        try:
            owner = await self.fetch_user(BOT_OWNER_ID)
            print(f"👤 봇 소유자: {owner.name} (ID: {owner.id})")
        except:
            print(f"⚠️ 경고: BOT_OWNER_ID({BOT_OWNER_ID})가 올바르지 않습니다!")
        
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game("마인크래프트 서버 관리 🎮")
        )
        
        print(f"\n📋 관리 중인 서버: {len(self.mc.servers_config)}개")
        for server_id, config in self.mc.servers_config.items():
            status = "🟢" if self.mc.is_process_running(server_id) else "🔴"
            
            memory_config = config.get('memory', {})
            min_mem = memory_config.get('min', 'N/A')
            max_mem = memory_config.get('max', 'N/A')
            memory = f"{min_mem}-{max_mem}MB"
            
            print(f"   {status} [{server_id}] {config.get('name', server_id)} ({memory})")
        
        if ENABLE_AUTO_SHUTDOWN:
            print(f"\n⏰ 자동 종료: 활성화 ({EMPTY_SERVER_TIMEOUT}분 대기)")
            if AUTO_STOP_INSTANCE:
                print(f"☁️ GCP 자동 중지: 활성화")
        
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
        
        # 자동 종료 모니터링 중지
        if hasattr(self, 'check_empty_servers') and self.check_empty_servers.is_running():
            self.check_empty_servers.cancel()
        
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