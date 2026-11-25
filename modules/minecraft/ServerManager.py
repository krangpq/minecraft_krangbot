"""
마인크래프트 서버 관리 매니저
경로: modules/minecraft/ServerManager.py

실행 방식 (서버 설정의 terminal_mode)
  - "process" (Windows 기본): java 를 직접 실행, PID 파일로 추적·재연결 → ProcessManager
  - "screen" / "separate" / "background" (Linux 등 예전 방식): ScreenManager/TerminalLauncher

process 모드 중지 절차
  정상: RCON stop (RCON 이 안 되면 콘솔에 Ctrl+C) → STOP_TIMEOUT 초 대기
        → 그래도 안 꺼지면 AUTO_FORCE_KILL_ON_TIMEOUT 이 True 일 때만 강제 종료, 아니면 알리기만
  강제: RCON save-all flush → Ctrl+C → FORCE_STOP_GRACE 초 대기 → 프로세스 강제 종료
"""

import asyncio
import json
import socket
import subprocess
import psutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
from mcstatus import JavaServer
import platform

import settings
from .PortManager import PortManager
from .ProcessManager import ProcessManager, TrackedProcess
from . import LaunchResolver

# RCON 클라이언트
try:
    from .RconClient import RconClient
    RCON_AVAILABLE = True
except ImportError:
    RCON_AVAILABLE = False
    print("⚠️ RCON 클라이언트를 불러올 수 없습니다.")

# Screen/Terminal 관리자 (Linux 예전 방식)
try:
    from .ScreenManager import TerminalLauncher, ScreenManager
    SCREEN_AVAILABLE = True
except ImportError:
    SCREEN_AVAILABLE = False
    print("⚠️ ScreenManager를 불러올 수 없습니다.")


def _setting(name, default):
    return getattr(settings, name, default)


def make_process_manager() -> ProcessManager:
    return ProcessManager(
        state_dirname=_setting("SERVER_STATE_DIRNAME", ".krangbot"),
        console_mode=_setting("SERVER_CONSOLE_MODE", "minimized"),
    )


def read_bot_config(server_path: Path) -> dict:
    """bot_config.json 읽기만 (없거나 깨졌으면 빈 dict, 새로 만들지 않음)"""
    f = Path(server_path) / "bot_config.json"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _fmt_mb(mb: int) -> str:
    return f"{mb // 1024}GB" if mb % 1024 == 0 else f"{mb}MB"


def _tail_text(path: Path, lines: int = 15, since: Optional[float] = None) -> Optional[str]:
    try:
        if since is not None and path.stat().st_mtime < since - 2:
            return None
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8000))
            text = f.read().decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    except OSError:
        return None


class ServerManager:
    """마인크래프트 서버 관리"""

    def __init__(self, bot, base_path: str, servers_config: dict, default_server: str,
                 process_manager: Optional[ProcessManager] = None):
        self.bot = bot
        self.base_path = Path(base_path)
        self.servers_config = servers_config
        self.default_server = default_server

        # 실행 중인 서버: {server_id: TrackedProcess | screen 세션 이름(str) | subprocess.Popen}
        self.running_servers = {}
        self.server_screen_sessions = {}  # {server_id: screen_session_name}

        # RCON 클라이언트
        self.rcon_clients = {}

        # 동시 실행 방지용 Lock
        self.server_locks = {}  # {server_id: asyncio.Lock}

        # 서버 상태 캐시
        self.server_status = {}

        # 디렉토리
        self.servers_dir = self.base_path / 'servers'
        self.logs_dir = self.base_path / 'logs'
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # OS 타입
        self.os_type = platform.system()

        # process 모드 관리자 (스캐너와 같은 인스턴스를 받으면 스캔 때 찾은 결과를 그대로 씀)
        self.pm = process_manager or make_process_manager()

        # 터미널 런처 (예전 방식)
        if SCREEN_AVAILABLE and self._any_legacy_mode():
            self.terminal_launcher = TerminalLauncher()
            print(f"✅ 터미널 런처 초기화 (OS: {self.os_type})")
            if self.os_type == "Linux":
                if ScreenManager.is_screen_available():
                    print("✅ Screen 사용 가능")
                else:
                    print("⚠️ Screen 미설치 - 백그라운드 모드 사용")
        else:
            self.terminal_launcher = None

        # 기존 실행 중인 서버 재연결 (RCON 초기화 전에!)
        self._reconnect_existing_servers()

        # RCON 초기화
        self._init_rcon_clients()

    # ============================================
    # 공통
    # ============================================

    def _uses_process(self, server_id: str) -> bool:
        config = self.servers_config.get(server_id) or {}
        return config.get('terminal_mode', 'process') == 'process'

    def _any_legacy_mode(self) -> bool:
        return any(c.get('terminal_mode', 'process') != 'process' for c in self.servers_config.values())

    def _lock(self, server_id: str) -> asyncio.Lock:
        if server_id not in self.server_locks:
            self.server_locks[server_id] = asyncio.Lock()
        return self.server_locks[server_id]

    def _reconnect_existing_servers(self):
        """봇 재시작 시 이미 켜져 있는 서버 다시 연결"""
        print("\n🔄 기존 실행 중인 서버 확인 중...")
        adopt = _setting("ADOPT_EXTERNAL_SERVERS", True)
        reconnected = 0

        for server_id, config in self.servers_config.items():
            if not self._uses_process(server_id):
                continue
            t = self.pm.find_running(server_id, Path(config['path']), adopt_external=adopt)
            if t:
                self.running_servers[server_id] = t
                kind = "외부 실행" if t.external else "봇이 실행"
                print(f"   ♻️ 재연결: {config['name']} (PID {t.pid}, {kind})")
                reconnected += 1

        # 예전 방식: Linux screen
        if self.os_type == "Linux" and SCREEN_AVAILABLE and self._any_legacy_mode():
            all_screens = ScreenManager.list_screens(filter_prefix="minecraft_")
            for server_id, config in self.servers_config.items():
                if self._uses_process(server_id):
                    continue
                actual_session = ScreenManager.find_screen_by_name(f"minecraft_{server_id}") if all_screens else None
                if actual_session:
                    print(f"   ♻️ 재연결: {config['name']} ({actual_session})")
                    self.running_servers[server_id] = actual_session
                    self.server_screen_sessions[server_id] = actual_session
                    reconnected += 1

        if reconnected:
            print(f"✅ {reconnected}개 서버 재연결 완료: {list(self.running_servers.keys())}\n")
        else:
            print("   💤 실행 중인 서버 없음\n")

    def _init_rcon_clients(self):
        """RCON 클라이언트 초기화"""
        if not RCON_AVAILABLE:
            return
        timeout = _setting("RCON_TIMEOUT", 5)
        for server_id, config in self.servers_config.items():
            rcon_config = config.get('rcon', {})
            if rcon_config.get('enabled', False):
                try:
                    self.rcon_clients[server_id] = RconClient(
                        host=rcon_config.get('host', 'localhost'),
                        port=rcon_config.get('port', PortManager.DEFAULT_RCON_PORT),
                        password=rcon_config.get('password', ''),
                        timeout=timeout,
                    )
                except Exception as e:
                    print(f"⚠️ RCON 초기화 실패 ({server_id}): {e}")

    def get_server_config(self, server_id: str = None) -> Optional[dict]:
        """서버 설정 가져오기"""
        if server_id is None:
            server_id = self.default_server
        return self.servers_config.get(server_id)

    def get_all_server_ids(self) -> list:
        """모든 서버 ID 목록"""
        return list(self.servers_config.keys())

    @staticmethod
    def _port_listening(port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            return sock.connect_ex(('localhost', port)) == 0
        except OSError:
            return False
        finally:
            sock.close()

    def is_server_running(self, server_id: str) -> bool:
        """서버가 켜져서 접속 가능한지 (프로세스 + 게임 포트 열림)"""
        if not self.is_process_running(server_id):
            return False

        obj = self.running_servers[server_id]
        if isinstance(obj, subprocess.Popen):
            return True

        config = self.get_server_config(server_id)
        if config:
            return self._port_listening(config['port'])
        return True

    def is_process_running(self, server_id: str) -> bool:
        """프로세스 실행 여부만 확인 (포트 체크 안 함)"""
        if server_id not in self.running_servers:
            return False

        obj = self.running_servers[server_id]

        if isinstance(obj, TrackedProcess):
            if self.pm.is_alive(server_id):
                return True
            self.running_servers.pop(server_id, None)
            return False

        # Screen 세션인 경우
        if isinstance(obj, str) and SCREEN_AVAILABLE:
            return ScreenManager.screen_exists(obj)

        # Popen 프로세스인 경우
        if isinstance(obj, subprocess.Popen):
            return obj.poll() is None

        return False

    def is_external(self, server_id: str) -> bool:
        obj = self.running_servers.get(server_id)
        return isinstance(obj, TrackedProcess) and obj.external

    def has_rcon(self, server_id: str) -> bool:
        """서버가 RCON을 지원하는지 확인"""
        return server_id in self.rcon_clients

    # ============================================
    # 시작
    # ============================================

    async def start_server(self, server_id: str) -> Tuple[bool, str]:
        """서버 시작 (Lock으로 동시 실행 방지)"""
        try:
            async with self._lock(server_id):
                config = self.get_server_config(server_id)
                if not config:
                    return False, f"서버 설정을 찾을 수 없습니다: {server_id}"

                if self.is_process_running(server_id):
                    return False, f"⚠️ {config['name']} 서버가 이미 실행 중입니다.\n💡 서버 시작 중이라면 잠시 기다려주세요."

                server_path = Path(config['path'])
                if not server_path.exists():
                    return False, f"서버 경로가 존재하지 않습니다: {server_path}"

                if self._uses_process(server_id):
                    return await self._start_process(server_id, config, server_path)

                return await self._start_legacy(server_id, config, server_path)

        except Exception as e:
            print(f"❌ 서버 시작 오류: {e}")
            import traceback
            traceback.print_exc()
            return False, f"오류 발생: {e}"

    def _port_conflict(self, server_id: str, port: int) -> Optional[str]:
        """같은 게임 포트를 쓰는 다른 서버가 켜져 있으면 그 이름"""
        for other_id, other in self.servers_config.items():
            if other_id == server_id or other.get('port') != port:
                continue
            if self.is_process_running(other_id):
                return other.get('name', other_id)
            # 봇이 모르는 사이에 켜진 경우도 확인
            if self._uses_process(other_id) and _setting("ADOPT_EXTERNAL_SERVERS", True):
                t = self.pm.find_running(other_id, Path(other['path']), adopt_external=True)
                if t:
                    self.running_servers[other_id] = t
                    return other.get('name', other_id)
        return None

    async def _start_process(self, server_id: str, config: dict, server_path: Path) -> Tuple[bool, str]:
        name = config['name']

        # 봇이 모르는 사이에 이 서버가 켜졌는지 (run.bat 직접 실행 등)
        t = self.pm.find_running(server_id, server_path, adopt_external=_setting("ADOPT_EXTERNAL_SERVERS", True))
        if t:
            self.running_servers[server_id] = t
            return False, f"⚠️ {name} 서버가 이미 실행 중입니다 (PID {t.pid}{', 봇 밖에서 켬' if t.external else ''})."

        port = config['port']
        other = self._port_conflict(server_id, port)
        if other:
            return False, (f"같은 포트({port})를 쓰는 **{other}** 서버가 켜져 있어서 동시에 켤 수 없습니다.\n"
                           f"💡 먼저 그 서버를 중지하세요.")
        if not PortManager.is_port_open(port):
            return False, f"게임 포트 {port} 를 다른 프로그램이 쓰고 있어서 시작할 수 없습니다."

        # 시작 명령 (지금 파일 기준으로 다시 결정 → user_jvm_args.txt 수정이 바로 반영됨)
        bot_config = read_bot_config(server_path)
        plan, why = LaunchResolver.resolve_launch(
            server_path, bot_config,
            _setting("DEFAULT_MIN_MEMORY", 1024), _setting("DEFAULT_MAX_MEMORY", 4096))
        if plan is None:
            return False, f"시작 명령을 정할 수 없습니다: {why}"
        for w in plan.warnings:
            print(f"   ⚠️ {w}")

        ok, msg = self._check_system_memory(plan.memory_max_mb)
        if not ok:
            return False, msg

        java, java_reason = LaunchResolver.select_java(
            LaunchResolver.required_java_major(plan.mc_version),
            explicit=bot_config.get("java"),
            java_paths=_setting("JAVA_PATHS", {}),
            auto_detect=_setting("JAVA_AUTO_DETECT", True),
            default_java=_setting("DEFAULT_JAVA", "java"),
        )
        argv = [java] + plan.args

        print(f"🚀 서버 시작: {name}")
        print(f"   경로: {server_path}")
        print(f"   방식: {plan.describe()} / Java: {java} ({java_reason})")
        print(f"   명령: {subprocess.list2cmdline(argv)}")

        rcon = config.get('rcon', {})
        extra = {
            "game_port": port,
            "rcon_enabled": bool(rcon.get('enabled')),
            "rcon_port": rcon.get('port'),
            "launch_kind": plan.kind,
            "profile": _setting("PROFILE", None),
        }
        launched_at = datetime.now().timestamp()
        try:
            ok, msg, tracked = await asyncio.to_thread(
                self.pm.launch, server_id, server_path, argv, extra, f"[크랑봇] {name}")
        except FileNotFoundError:
            return False, f"Java 를 찾을 수 없습니다: `{java}`\n💡 bot_config.json 의 \"java\" 또는 settings 의 JAVA_PATHS 를 확인하세요."
        except OSError as e:
            return False, f"서버 프로세스 실행 실패: {e}"
        if not ok:
            return False, msg

        self.running_servers[server_id] = tracked

        # 바로 죽지 않는지 확인 (Java 버전 불일치, 메모리 부족, 설정 오류 등은 몇 초 안에 죽음)
        check = float(_setting("START_CHECK_SECONDS", 15))
        waited = 0.0
        while waited < check:
            await asyncio.sleep(0.5)
            waited += 0.5
            if not self.pm.is_alive(server_id):
                self.running_servers.pop(server_id, None)
                tail = _tail_text(server_path / "logs" / "latest.log", since=launched_at)
                text = f"{name} 서버가 시작 직후 종료됐습니다 ({waited:.0f}초)."
                text += f"\nJava: `{java}` ({java_reason})"
                if tail:
                    text += f"\n```\n{tail[-1500:]}\n```"
                else:
                    text += "\n💡 로그가 남지 않았어요. Java 버전이나 메모리 설정 문제일 수 있습니다 (서버 폴더에서 run.bat 으로 직접 실행해 확인)."
                return False, text

        mem = f", 메모리 최대 {_fmt_mb(plan.memory_max_mb)}" if plan.memory_max_mb else ""
        return True, (f"{name} 서버를 시작했습니다 (PID {tracked.pid}, {plan.describe()}{mem}).\n"
                      f"💡 모드팩은 접속 가능해질 때까지 몇 분 걸릴 수 있어요. `/서버상태` 로 확인하세요.")

    async def _start_legacy(self, server_id: str, config: dict, server_path: Path) -> Tuple[bool, str]:
        """예전 방식 (Linux screen 등)"""
        if self.is_server_running(server_id):
            return False, "서버가 이미 실행 중입니다."

        ok, msg = self._check_system_memory(config.get('memory', {}).get('max'))
        if not ok:
            return False, msg

        start_command = config['start_command']
        terminal_mode = config.get('terminal_mode', 'auto')

        print(f"🚀 서버 시작: {config['name']}")
        print(f"   경로: {server_path}")
        print(f"   명령어: {start_command}")
        print(f"   모드: {terminal_mode}")

        if self.terminal_launcher:
            if terminal_mode == "auto":
                use_screen = (self.os_type == "Linux")
            elif terminal_mode in ("screen", "separate"):
                use_screen = True
            else:  # "background"
                use_screen = False

            success, message, screen_session = await self.terminal_launcher.launch_server(
                server_id=server_id,
                command=start_command,
                cwd=str(server_path),
                use_screen=use_screen
            )

            if success and screen_session:
                self.running_servers[server_id] = screen_session
                self.server_screen_sessions[server_id] = screen_session
                await asyncio.sleep(3)
                return True, message
            elif success:
                await asyncio.sleep(3)
                return True, message
            else:
                return False, message

        return await self._start_background(server_id, start_command, server_path)

    async def _start_background(self, server_id: str, command: str, cwd: Path) -> Tuple[bool, str]:
        """백그라운드 모드로 서버 시작 (예전 방식)"""
        try:
            log_file = self.logs_dir / f"{server_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=str(cwd),
                stdout=open(log_file, 'w', encoding='utf-8'),
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE
            )

            self.running_servers[server_id] = process

            await asyncio.sleep(5)

            if process.poll() is None:
                return True, "서버가 백그라운드에서 시작되었습니다."
            else:
                return False, "서버 시작에 실패했습니다."

        except Exception as e:
            return False, f"백그라운드 시작 오류: {e}"

    # ============================================
    # 중지
    # ============================================

    async def stop_server(self, server_id: str, force: bool = False) -> Tuple[bool, str]:
        """서버 중지 (Lock으로 동시 실행 방지)"""
        try:
            async with self._lock(server_id):
                config = self.get_server_config(server_id)
                if not config:
                    return False, f"서버 설정을 찾을 수 없습니다: {server_id}"

                print(f"\n🛑 서버 중지 시도: {server_id} (강제: {force})")

                if self._uses_process(server_id):
                    # 봇이 모르는 사이에 켜진 서버도 끌 수 있게
                    if not self.is_process_running(server_id):
                        t = self.pm.find_running(server_id, Path(config['path']),
                                                 adopt_external=_setting("ADOPT_EXTERNAL_SERVERS", True))
                        if t:
                            self.running_servers[server_id] = t
                    if not self.is_process_running(server_id):
                        return False, "서버가 실행 중이 아닙니다."
                    if force:
                        return await self._force_stop_process(server_id, config)
                    return await self._stop_process(server_id, config)

                if not self.is_process_running(server_id):
                    return False, "서버가 실행 중이 아닙니다."
                return await self._stop_legacy(server_id, config, force)

        except Exception as e:
            print(f"❌ 서버 중지 오류: {e}")
            import traceback
            traceback.print_exc()
            return False, f"오류 발생: {e}"

    async def _stop_process(self, server_id: str, config: dict) -> Tuple[bool, str]:
        name = config['name']
        how = None
        if self.has_rcon(server_id):
            sent, resp = await self.rcon_clients[server_id].send_stop()
            if sent:
                how = "RCON stop"
            else:
                print(f"   ⚠️ RCON stop 실패: {resp}")
        if how is None:
            if await asyncio.to_thread(self.pm.send_ctrl_c, server_id):
                how = "콘솔 Ctrl+C (RCON 불가)"
            else:
                return False, (f"{name} 서버에 중지 명령을 전달하지 못했습니다 (RCON 도 콘솔 Ctrl+C 도 실패).\n"
                               f"💡 `/서버중지 강제:True` 로 끌 수 있어요.")
        print(f"   📤 {how} 전송 → 종료 대기 (최대 {_setting('STOP_TIMEOUT', 180)}초)")

        timeout = float(_setting("STOP_TIMEOUT", 180))
        if await asyncio.to_thread(self.pm.wait_exit, server_id, timeout):
            self.pm.forget(server_id)
            self.running_servers.pop(server_id, None)
            return True, f"{name} 서버가 중지되었습니다. ({how})"

        if _setting("AUTO_FORCE_KILL_ON_TIMEOUT", False):
            print("   ⏱️ 시간 초과 → 강제 종료 (AUTO_FORCE_KILL_ON_TIMEOUT)")
            ok, msg = await self._force_stop_process(server_id, config)
            return ok, f"{int(timeout)}초 안에 안 꺼져서 강제 종료했습니다.\n{msg}"

        return False, (f"{name} 서버가 {int(timeout)}초가 지나도 아직 꺼지지 않았습니다 (중지 명령은 전달됨, 저장 중일 수 있음).\n"
                       f"💡 잠시 뒤 `/서버상태` 로 확인하고, 계속 안 꺼지면 `/서버중지 강제:True`")

    async def _force_stop_process(self, server_id: str, config: dict) -> Tuple[bool, str]:
        name = config['name']
        if self.has_rcon(server_id):
            ok, resp = await self.rcon_clients[server_id].save_all(flush=True)
            print(f"   💾 save-all flush: {'OK' if ok else resp}")

        grace = float(_setting("FORCE_STOP_GRACE", 30))
        if await asyncio.to_thread(self.pm.send_ctrl_c, server_id):
            print(f"   ⌨️ Ctrl+C 전송 → {grace:.0f}초 대기")
            if await asyncio.to_thread(self.pm.wait_exit, server_id, grace):
                self.pm.forget(server_id)
                self.running_servers.pop(server_id, None)
                return True, f"{name} 서버를 Ctrl+C 로 중지했습니다 (종료 시 저장됨)."

        print("   💥 프로세스 강제 종료")
        if not self.pm.kill(server_id):
            return False, f"{name} 서버 프로세스를 종료하지 못했습니다 (권한 부족?)."
        await asyncio.to_thread(self.pm.wait_exit, server_id, 10)
        self.pm.forget(server_id)
        self.running_servers.pop(server_id, None)
        return True, f"{name} 서버를 강제 종료했습니다. ⚠️ 마지막 저장 이후의 변경은 사라졌을 수 있어요."

    async def _stop_legacy(self, server_id: str, config: dict, force: bool) -> Tuple[bool, str]:
        obj = self.running_servers[server_id]

        # Screen 세션인 경우
        if isinstance(obj, str) and SCREEN_AVAILABLE:
            screen_session = obj
            if force:
                success, message = await ScreenManager().kill_screen(screen_session)
            else:
                success, message = await ScreenManager().send_to_screen(
                    screen_session,
                    config.get('stop_command', 'stop')
                )
                if success:
                    for i in range(60):
                        await asyncio.sleep(1)
                        if not ScreenManager.screen_exists(screen_session):
                            break
                    if ScreenManager.screen_exists(screen_session):
                        await ScreenManager().kill_screen(screen_session)
                        message += " (타임아웃으로 강제 종료)"

            del self.running_servers[server_id]
            self.server_screen_sessions.pop(server_id, None)
            return True, message

        # Popen 프로세스인 경우
        if isinstance(obj, subprocess.Popen):
            process = obj
            if force:
                process.terminate()
                await asyncio.sleep(2)
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    stop_cmd = config.get('stop_command', 'stop')
                    process.stdin.write(f"{stop_cmd}\n".encode())
                    process.stdin.flush()
                    for _ in range(60):
                        await asyncio.sleep(1)
                        if process.poll() is not None:
                            break
                    if process.poll() is None:
                        process.terminate()
                        await asyncio.sleep(2)
                        if process.poll() is None:
                            process.kill()
                except Exception:
                    process.terminate()

            del self.running_servers[server_id]
            return True, f"{config['name']} 서버가 중지되었습니다."

        return False, "알 수 없는 실행 방식입니다."

    async def restart_server(self, server_id: str) -> Tuple[bool, str]:
        """서버 재시작"""
        config = self.get_server_config(server_id)
        if not config:
            return False, f"서버 설정을 찾을 수 없습니다: {server_id}"

        print(f"🔄 서버 재시작: {config['name']}")

        if self.is_process_running(server_id):
            success, message = await self.stop_server(server_id)
            if not success:
                return False, f"서버 중지 실패: {message}"
            await asyncio.sleep(3)

        return await self.start_server(server_id)

    # ============================================
    # 명령 / 상태
    # ============================================

    async def send_command(self, server_id: str, command: str) -> Tuple[bool, str]:
        """서버에 명령어 전송 (RCON > Screen > stdin)"""
        # 1순위: RCON
        if self.has_rcon(server_id):
            success, response = await self.rcon_clients[server_id].execute_command(command)
            if success:
                print(f"📤 RCON: {command}")
                return True, f"```\n{response or '(응답 없음)'}\n```"
            if self._uses_process(server_id):
                hint = ""
                if self.is_external(server_id):
                    hint = "\n💡 봇 밖에서 켠 서버라 RCON 이 꺼진 설정으로 실행됐을 수 있어요 (봇으로 다시 켜면 해결)."
                return False, f"{response}{hint}"

        if self._uses_process(server_id):
            if not self.is_process_running(server_id):
                return False, "서버가 실행 중이 아닙니다."
            return False, "RCON 이 설정되지 않아 명령을 보낼 수 없습니다."

        # 2순위: Screen
        if server_id in self.server_screen_sessions and SCREEN_AVAILABLE:
            screen_session = self.server_screen_sessions[server_id]
            success, message = await ScreenManager().send_to_screen(screen_session, command)
            if success:
                return True, f"명령어가 전송되었습니다: `{command}`\n💡 Screen에 접속하여 결과를 확인하세요: `screen -r {screen_session}`"
            return False, message

        # 3순위: stdin
        if server_id in self.running_servers:
            obj = self.running_servers[server_id]
            if isinstance(obj, subprocess.Popen):
                try:
                    obj.stdin.write(f"{command}\n".encode())
                    obj.stdin.flush()
                    return True, f"명령어가 전송되었습니다: `{command}`\n⚠️ 결과 확인 불가 (RCON 권장)"
                except Exception:
                    return False, "명령어 전송 실패"

        return False, "서버가 실행 중이 아닙니다."

    def get_screen_info(self, server_id: str) -> Optional[dict]:
        """Screen 세션 정보"""
        if server_id not in self.server_screen_sessions:
            return None

        screen_session = self.server_screen_sessions[server_id]

        return {
            "session_name": screen_session,
            "attach_command": f"screen -r {screen_session}",
            "detach_keys": "Ctrl+A, D",
            "exists": ScreenManager.screen_exists(screen_session) if SCREEN_AVAILABLE else False
        }

    async def get_server_status(self, server_id: str) -> Optional[dict]:
        """서버 상태 조회 (타임아웃 추가)"""
        try:
            config = self.get_server_config(server_id)
            if not config:
                return None

            server = JavaServer.lookup(f"localhost:{config['port']}")

            try:
                status = await asyncio.wait_for(
                    asyncio.to_thread(server.status),
                    timeout=10.0
                )

                return {
                    "online": True,
                    "players": {
                        "online": status.players.online,
                        "max": status.players.max,
                        "names": [p.name for p in (status.players.sample or [])]
                    },
                    "version": status.version.name,
                    "latency": status.latency
                }
            except asyncio.TimeoutError:
                print(f"⚠️ [{server_id}] 서버 상태 조회 타임아웃")
                return {"online": False, "error": "timeout"}

        except Exception as e:
            return {"online": False, "error": str(e)}

    async def get_server_performance(self, server_id: str) -> Optional[dict]:
        """서버 성능 정보"""
        try:
            if not self.is_process_running(server_id):
                return None

            obj = self.running_servers[server_id]
            if isinstance(obj, TrackedProcess):
                ps_process = obj.proc
            elif isinstance(obj, subprocess.Popen):
                ps_process = psutil.Process(obj.pid)
            else:
                return None

            cpu = await asyncio.to_thread(ps_process.cpu_percent, 1)
            return {
                "cpu_percent": cpu,
                "memory_mb": ps_process.memory_info().rss / 1024 / 1024,
                "memory_percent": ps_process.memory_percent(),
                "threads": ps_process.num_threads(),
                "uptime_seconds": (datetime.now() - datetime.fromtimestamp(ps_process.create_time())).total_seconds(),
                "pid": ps_process.pid,
                "external": isinstance(obj, TrackedProcess) and obj.external,
            }
        except Exception as e:
            print(f"⚠️ 성능 정보 조회 실패: {e}")
            return None

    async def backup_world(self, server_id: str) -> Tuple[bool, str]:
        """월드 백업"""
        try:
            config = self.get_server_config(server_id)
            if not config:
                return False, f"서버 설정을 찾을 수 없습니다: {server_id}"

            server_path = Path(config['path'])
            world_path = server_path / "world"

            if not world_path.exists():
                return False, "월드 폴더가 존재하지 않습니다."

            backup_dir = server_path / "backups"
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"world_backup_{timestamp}"
            backup_path = backup_dir / backup_name

            # RCON으로 저장 명령 (서버 실행 중이면)
            if self.is_server_running(server_id) and self.has_rcon(server_id):
                rcon = self.rcon_clients[server_id]
                await rcon.save_all()
                await asyncio.sleep(2)  # 저장 완료 대기

            import shutil
            await asyncio.to_thread(
                shutil.make_archive,
                str(backup_path),
                'zip',
                str(world_path)
            )

            backup_file = f"{backup_path}.zip"
            backup_size = Path(backup_file).stat().st_size / (1024 * 1024)  # MB

            return True, (
                f"{config['name']} 월드 백업 완료!\n"
                f"파일: `{backup_name}.zip` ({backup_size:.1f}MB)\n"
                f"위치: `{backup_dir}`"
            )

        except Exception as e:
            print(f"❌ 백업 오류: {e}")
            return False, f"백업 실패: {e}"

    async def cleanup_on_shutdown(self):
        """봇 종료 시 정리"""
        running = [sid for sid in list(self.running_servers.keys()) if self.is_process_running(sid)]
        if not running:
            return
        if not _setting("STOP_SERVERS_ON_BOT_EXIT", False):
            print(f"\nℹ️ 켜져 있는 서버 {len(running)}개는 계속 실행됩니다 (STOP_SERVERS_ON_BOT_EXIT=False). "
                  f"봇을 다시 켜면 재연결합니다.")
            return

        print("\n🧹 서버 정리 중...")
        for server_id in running:
            config = self.get_server_config(server_id)
            print(f"   - {config['name']} 중지 중...")
            await self.stop_server(server_id, force=False)
        print("✅ 서버 정리 완료")

    def _check_system_memory(self, required_mb: Optional[int]) -> Tuple[bool, str]:
        """
        시스템 메모리가 충분한지 확인 (가용 RAM >= -Xmx + 여유분)

        Returns:
            (충분한지, 메시지)
        """
        if not _setting("MEMORY_CHECK_ENABLED", True):
            return True, "OK"
        if not required_mb:
            print("   ⚠️ 최대 메모리(-Xmx)를 몰라서 메모리 검사를 건너뜁니다")
            return True, "OK"
        try:
            buffer_mb = int(_setting("MEMORY_CHECK_BUFFER_MB", 1024))
            available_mb = psutil.virtual_memory().available / (1024 * 1024)
            required_with_buffer = required_mb + buffer_mb

            if available_mb < required_with_buffer:
                return False, (
                    f"❌ 시스템 메모리 부족!\n"
                    f"필요: {required_with_buffer:.0f}MB (-Xmx {required_mb}MB + 여유 {buffer_mb}MB)\n"
                    f"사용 가능: {available_mb:.0f}MB\n"
                    f"💡 다른 서버나 프로그램을 종료하거나 서버 메모리 설정을 낮춰주세요."
                )

            return True, "OK"

        except Exception as e:
            print(f"⚠️ 메모리 체크 오류: {e}")
            return True, "OK"  # 오류 시에는 통과
