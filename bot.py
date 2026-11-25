"""
마인크래프트 서버 관리 봇 본체
경로: bot.py

직접 실행하지 말고 run_prod.py / run_dev.py 로 실행하세요.
(진입 파일이 settings.activate() 로 프로필을 먼저 불러옴)
"""

import discord
from discord.ext import commands, tasks
import signal
import sys
import asyncio
from datetime import datetime

import settings
from settings import (
    TOKEN,
    BOT_OWNER_ID,
    BASE_PATH,
    SERVERS_DIR,
    DATA_DIR,
    DEV_GUILD_ID,
    AUTO_SCAN_SERVERS,
    MINECRAFT_SERVERS,
    DEFAULT_TERMINAL_MODE,
    DEFAULT_MIN_MEMORY,
    DEFAULT_MAX_MEMORY,
    UPDATE_CORES_ON_START,
    ENABLE_AUTO_SHUTDOWN,
    EMPTY_SERVER_TIMEOUT,
    AUTO_SHUTDOWN_WARNING_TIME,
)

# 마인크래프트 모듈
from modules.minecraft import (
    ServerManager,
    ServerScanner,
    ServerConfigurator,
    ServerCoreManager,
    ServerLifecycleManager,
    setup_commands as setup_mc_commands,
    setup_lifecycle_commands
)

# 권한 모듈
from modules.permissions import (
    PermissionManager,
    PermissionTree,
    audit_permission_table,
    setup_permission_commands,
)


class MinecraftBot(commands.Bot):
    """마인크래프트 서버 관리 봇 클래스"""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        # PermissionTree: 모든 슬래시 명령어 실행 전에 화이트리스트 등급 검사
        super().__init__(command_prefix='!', intents=intents, tree_cls=PermissionTree)

        # 권한(화이트리스트) 관리자
        self.permissions = PermissionManager(DATA_DIR / "permissions.json", owner_id=BOT_OWNER_ID)

        # 구동기 관리자 초기화
        self.core_manager = ServerCoreManager(BASE_PATH)
        print("구동기 관리자 초기화")

        # 서버 생명주기 관리자 초기화
        self.lifecycle_manager = ServerLifecycleManager(SERVERS_DIR, self.core_manager)
        print("생명주기 관리자 초기화")

        # 서버 설정 준비
        servers_config = self._prepare_servers()

        # 서버 매니저 초기화
        self.mc = ServerManager(
            bot=self,
            base_path=str(BASE_PATH),
            servers_config=servers_config,
            default_server=self._get_default_server(servers_config)
        )

        # 빈 서버 자동 종료 상태 추적
        self.empty_since = {}  # {server_id: datetime}
        self.shutdown_notified = {}  # {server_id: bool}

        # 종료 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

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
        if UPDATE_CORES_ON_START:
            print("\n구동기 업데이트 시작...")
            await self.core_manager.update_all_cores()
            print("구동기 업데이트 완료\n")
        else:
            print("\n구동기 자동 업데이트 꺼짐 (필요하면 /구동기업데이트)")

        setup_mc_commands(self)
        setup_lifecycle_commands(self)
        setup_permission_commands(self)

        # 권한표와 실제 명령어 비교 (표에 없는 명령어는 소유자 전용으로 막힘)
        audit_permission_table(self.tree)

        print(f"등록된 명령어 수: {len(self.tree.get_commands())}")

        if DEV_GUILD_ID:
            guild = discord.Object(id=DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"슬래시 명령어 동기화 완료 (테스트 길드 {DEV_GUILD_ID} 전용)")
        else:
            await self.tree.sync()
            print("슬래시 명령어 동기화 완료 (전역)")

        # 백업 정리
        await self.lifecycle_manager.cleanup_old_backups()

        # 빈 서버 자동 종료 모니터링 시작
        if ENABLE_AUTO_SHUTDOWN:
            self.check_empty_servers.start()
            print(f"빈 서버 자동 종료 모니터링 시작 (대기: {EMPTY_SERVER_TIMEOUT}분)")

    @tasks.loop(minutes=1)
    async def check_empty_servers(self):
        """플레이어가 없는 서버를 주기적으로 확인해서 자동 종료"""
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

                # 서버 상태 조회 (타임아웃 처리)
                try:
                    status = await asyncio.wait_for(
                        self.mc.get_server_status(server_id),
                        timeout=15.0
                    )
                except asyncio.TimeoutError:
                    print(f"⚠️ [{server_id}] 서버 상태 확인 타임아웃 - 카운터 초기화")
                    # 타임아웃 시 안전하게 카운터 초기화
                    if server_id in self.empty_since:
                        del self.empty_since[server_id]
                    if server_id in self.shutdown_notified:
                        del self.shutdown_notified[server_id]
                    continue
                except Exception as e:
                    print(f"⚠️ [{server_id}] 상태 확인 오류: {e}")
                    continue

                if not status or not status.get('online'):
                    # 상태 조회 실패 시에는 카운터 유지 (변경 없음)
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
            import traceback
            traceback.print_exc()

    async def auto_shutdown_server(self, server_id: str):
        """빈 서버 저장 후 종료"""
        try:
            print(f"📦 [{server_id}] 월드 저장 중...")
            # RCON으로 저장 시도
            if self.mc.has_rcon(server_id):
                await self.mc.send_command(server_id, "save-all")
                await asyncio.sleep(5)

            print(f"🛑 [{server_id}] 마인크래프트 서버 중지 중...")
            success, message = await self.mc.stop_server(server_id, force=False)

            if success:
                print(f"✅ [{server_id}] 서버 중지 완료")
            else:
                print(f"❌ [{server_id}] 서버 중지 실패: {message}")

            # 상태 초기화
            if server_id in self.empty_since:
                del self.empty_since[server_id]
            if server_id in self.shutdown_notified:
                del self.shutdown_notified[server_id]

        except Exception as e:
            print(f"❌ 자동 종료 오류: {e}")

    async def on_ready(self):
        """봇 준비 완료"""
        print("\n" + "="*60)
        print(f"🤖 Logged on as {self.user}!")
        print("="*60)

        try:
            owner = await self.fetch_user(BOT_OWNER_ID)
            print(f"👤 봇 소유자: {owner.name} (ID: {owner.id})")
        except Exception:
            print(f"⚠️ 경고: BOT_OWNER_ID({BOT_OWNER_ID})가 올바르지 않습니다!")

        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game("마인크래프트 서버 관리 🎮")
        )

        print(f"\n🌍 프로필: {settings.PROFILE} / OS: {settings.OS_TYPE}")
        print(f"📁 서버 폴더: {SERVERS_DIR}")
        print(f"🔐 화이트리스트: {len(self.permissions.users)}명 (+소유자)")

        print(f"\n📋 관리 중인 서버: {len(self.mc.servers_config)}개")
        for server_id, config in self.mc.servers_config.items():
            status = "🟢" if self.mc.is_process_running(server_id) else "🔴"

            memory_config = config.get('memory', {})
            min_mem = memory_config.get('min', 'N/A')
            max_mem = memory_config.get('max', 'N/A')
            memory = f"{min_mem}-{max_mem}MB"

            print(f"   {status} [{server_id}] {config.get('name', server_id)} ({memory})")

        if ENABLE_AUTO_SHUTDOWN:
            print(f"\n⏰ 빈 서버 자동 종료: 활성화 ({EMPTY_SERVER_TIMEOUT}분 대기)")

        print("\n" + "="*60)
        print("🚀 봇이 준비되었습니다!")
        print("💡 Discord에서 /서버목록 을 입력하여 서버를 확인하세요")
        print("💡 /권한 부여 로 친구들을 화이트리스트에 넣을 수 있습니다")
        print("="*60 + "\n")

    async def on_error(self, event, *args, **kwargs):
        """에러 처리"""
        import traceback
        print(f"\n❌ 오류 발생 (이벤트: {event})")
        traceback.print_exc()

    async def close(self):
        """봇 종료"""
        print("\n👋 봇을 종료합니다...")

        # Spigot 빌드 완료 대기 (안전장치)
        if self.core_manager.building_spigot:
            print("\n⚠️ Spigot 빌드 진행 중 - 완료 대기")
            await self.core_manager.wait_for_builds_completion()

        # 자동 종료 모니터링 중지
        if hasattr(self, 'check_empty_servers') and self.check_empty_servers.is_running():
            self.check_empty_servers.cancel()

        await self.mc.cleanup_on_shutdown()
        await super().close()


def main():
    """봇 실행 (run_prod.py / run_dev.py 에서 호출)"""
    settings.require_active()
    try:
        bot = MinecraftBot()
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("\n" + "="*60)
        print("❌ 로그인 실패: 봇 토큰이 올바르지 않습니다!")
        print("="*60)
        print("\n💡 해결 방법:")
        print(f"1. profiles/{settings.PROFILE}.py 파일을 열어주세요")
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
    settings.require_active()
