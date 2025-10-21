"""
마인크래프트 서버 관리 매니저 (Screen 통합)
경로: modules/minecraft/ServerManager.py
"""

import asyncio
import subprocess
import psutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
from mcstatus import JavaServer
import platform

# RCON 클라이언트
try:
    from .RconClient import RconClient
    RCON_AVAILABLE = True
except ImportError:
    RCON_AVAILABLE = False

# Screen 관리자
try:
    from .ScreenManager import TerminalLauncher, ScreenManager
    SCREEN_AVAILABLE = True
except ImportError:
    # 파일이 없으면 위의 코드를 ScreenManager.py로 저장
    SCREEN_AVAILABLE = False


class ServerManager:
    """마인크래프트 서버 관리 (Screen 지원)"""
    
    def __init__(self, bot, base_path: str, servers_config: dict, default_server: str):
        self.bot = bot
        self.base_path = Path(base_path)
        self.servers_config = servers_config
        self.default_server = default_server
        
        # 실행 중인 서버 프로세스/세션 추적
        self.running_servers = {}  # {server_id: subprocess.Popen or screen_session_name}
        self.server_screen_sessions = {}  # {server_id: screen_session_name}
        
        # RCON 클라이언트
        self.rcon_clients = {}
        
        # 서버 상태 캐시
        self.server_status = {}
        
        # 디렉토리
        self.servers_dir = self.base_path / 'servers'
        self.logs_dir = self.base_path / 'logs'
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # OS 타입
        self.os_type = platform.system()
        
        # 터미널 런처
        if SCREEN_AVAILABLE:
            self.terminal_launcher = TerminalLauncher()
            print(f"✅ 터미널 런처 초기화 (OS: {self.os_type})")
            if self.os_type == "Linux":
                if ScreenManager.is_screen_available():
                    print(f"✅ Screen 사용 가능")
                else:
                    print(f"⚠️ Screen 미설치 - 백그라운드 모드 사용")
        else:
            self.terminal_launcher = None
            print(f"⚠️ 터미널 런처 없음 - 기본 모드만 사용")
        
        # RCON 초기화
        self._init_rcon_clients()
    
    def _init_rcon_clients(self):
        """RCON 클라이언트 초기화"""
        if not RCON_AVAILABLE:
            return
        
        for server_id, config in self.servers_config.items():
            rcon_config = config.get('rcon', {})
            if rcon_config.get('enabled', False):
                try:
                    self.rcon_clients[server_id] = RconClient(
                        host=rcon_config.get('host', 'localhost'),
                        port=rcon_config.get('port', 25575),
                        password=rcon_config.get('password', '')
                    )
                    print(f"✅ RCON 초기화: {config['name']}")
                except Exception as e:
                    print(f"⚠️ RCON 초기화 실패 ({server_id}): {e}")
    
    def get_server_config(self, server_id: str = None) -> Optional[dict]:
        """서버 설정 가져오기"""
        if server_id is None:
            server_id = self.default_server
        return self.servers_config.get(server_id)
    
    def is_server_running(self, server_id: str) -> bool:
        """서버 실행 여부 확인"""
        if server_id not in self.running_servers:
            return False
        
        obj = self.running_servers[server_id]
        
        # Screen 세션인 경우
        if isinstance(obj, str):
            return ScreenManager.screen_exists(obj)
        
        # Popen 프로세스인 경우
        if isinstance(obj, subprocess.Popen):
            return obj.poll() is None
        
        return False
    
    async def start_server(self, server_id: str) -> Tuple[bool, str]:
        """
        서버 시작
        
        config.py 설정:
        - Linux: "terminal_mode": "screen" (기본) 또는 "background"
        - Windows: "terminal_mode": "separate" 또는 "background"
        - macOS: "terminal_mode": "separate" 또는 "background"
        """
        try:
            if self.is_server_running(server_id):
                return False, "서버가 이미 실행 중입니다."
            
            config = self.get_server_config(server_id)
            if not config:
                return False, f"서버 설정을 찾을 수 없습니다: {server_id}"
            
            server_path = Path(config['path'])
            if not server_path.exists():
                return False, f"서버 경로가 존재하지 않습니다: {server_path}"
            
            start_command = config['start_command']
            terminal_mode = config.get('terminal_mode', 'auto')
            
            print(f"🚀 서버 시작: {config['name']}")
            print(f"   경로: {server_path}")
            print(f"   명령어: {start_command}")
            print(f"   모드: {terminal_mode}")
            
            # 터미널 런처 사용 가능한 경우
            if self.terminal_launcher:
                # terminal_mode 결정
                if terminal_mode == "auto":
                    # Linux면 screen, 아니면 separate
                    use_screen = (self.os_type == "Linux")
                elif terminal_mode == "screen":
                    use_screen = True
                elif terminal_mode == "separate":
                    use_screen = True
                else:  # "background"
                    use_screen = False
                
                success, message, screen_session = await self.terminal_launcher.launch_server(
                    server_id=server_id,
                    command=start_command,
                    cwd=str(server_path),
                    use_screen=use_screen
                )
                
                if success:
                    if screen_session:
                        # Screen 세션으로 시작됨
                        self.running_servers[server_id] = screen_session
                        self.server_screen_sessions[server_id] = screen_session
                    
                    await asyncio.sleep(3)
                    return True, message
                else:
                    return False, message
            
            # 폴백: 기본 백그라운드 실행
            else:
                return await self._start_background(server_id, start_command, server_path)
                
        except Exception as e:
            print(f"❌ 서버 시작 오류: {e}")
            return False, f"오류 발생: {e}"
    
    async def _start_background(self, server_id: str, command: str, cwd: Path) -> Tuple[bool, str]:
        """백그라운드 모드로 서버 시작 (폴백)"""
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
    
    async def stop_server(self, server_id: str, force: bool = False) -> Tuple[bool, str]:
        """서버 중지"""
        try:
            if not self.is_server_running(server_id):
                return False, "서버가 실행 중이 아닙니다."
            
            config = self.get_server_config(server_id)
            obj = self.running_servers[server_id]
            
            print(f"🛑 서버 중지: {config['name']}")
            
            # Screen 세션인 경우
            if isinstance(obj, str):
                screen_session = obj
                
                if force:
                    # 강제 종료
                    success, message = await ScreenManager().kill_screen(screen_session)
                else:
                    # 정상 종료 (stop 명령어 전송)
                    success, message = await ScreenManager().send_to_screen(
                        screen_session,
                        config.get('stop_command', 'stop')
                    )
                    
                    if success:
                        # 종료될 때까지 대기 (최대 60초)
                        for _ in range(60):
                            await asyncio.sleep(1)
                            if not ScreenManager.screen_exists(screen_session):
                                break
                        
                        # 아직 실행 중이면 강제 종료
                        if ScreenManager.screen_exists(screen_session):
                            await ScreenManager().kill_screen(screen_session)
                            message += " (타임아웃으로 강제 종료)"
                
                # 정리
                del self.running_servers[server_id]
                if server_id in self.server_screen_sessions:
                    del self.server_screen_sessions[server_id]
                
                return True, message
            
            # Popen 프로세스인 경우
            elif isinstance(obj, subprocess.Popen):
                process = obj
                
                if force:
                    process.terminate()
                    await asyncio.sleep(2)
                    if process.poll() is None:
                        process.kill()
                else:
                    # stop 명령어 전송
                    try:
                        stop_cmd = config.get('stop_command', 'stop')
                        process.stdin.write(f"{stop_cmd}\n".encode())
                        process.stdin.flush()
                        
                        # 대기
                        for _ in range(60):
                            await asyncio.sleep(1)
                            if process.poll() is not None:
                                break
                        
                        # 타임아웃
                        if process.poll() is None:
                            process.terminate()
                            await asyncio.sleep(2)
                            if process.poll() is None:
                                process.kill()
                    except:
                        process.terminate()
                
                del self.running_servers[server_id]
                return True, f"{config['name']} 서버가 중지되었습니다."
                
        except Exception as e:
            print(f"❌ 서버 중지 오류: {e}")
            return False, f"오류 발생: {e}"
    
    async def send_command(self, server_id: str, command: str) -> Tuple[bool, str]:
        """서버에 명령어 전송 (RCON > Screen > stdin 순서)"""
        config = self.get_server_config(server_id)
        
        # 1순위: RCON
        if server_id in self.rcon_clients:
            try:
                rcon = self.rcon_clients[server_id]
                success, response = await rcon.execute_command(command)
                
                if success:
                    print(f"📤 RCON: {command}")
                    print(f"📥 응답: {response}")
                    return True, f"```\n{response}\n```"
                else:
                    # RCON 실패 시 다음 방법 시도
                    pass
            except:
                pass
        
        # 2순위: Screen
        if server_id in self.server_screen_sessions:
            screen_session = self.server_screen_sessions[server_id]
            success, message = await ScreenManager().send_to_screen(screen_session, command)
            
            if success:
                return True, f"명령어가 전송되었습니다: `{command}`\n💡 Screen에 접속하여 결과를 확인하세요: `screen -r {screen_session}`"
            else:
                return False, message
        
        # 3순위: stdin (Popen)
        if server_id in self.running_servers:
            obj = self.running_servers[server_id]
            if isinstance(obj, subprocess.Popen):
                try:
                    obj.stdin.write(f"{command}\n".encode())
                    obj.stdin.flush()
                    return True, f"명령어가 전송되었습니다: `{command}`\n⚠️ 결과 확인 불가 (RCON 권장)"
                except:
                    return False, "명령어 전송 실패"
        
        return False, "서버가 실행 중이 아닙니다."
    
    def get_screen_info(self, server_id: str) -> Optional[dict]:
        """Screen 세션 정보 가져오기"""
        if server_id not in self.server_screen_sessions:
            return None
        
        screen_session = self.server_screen_sessions[server_id]
        
        return {
            "session_name": screen_session,
            "attach_command": f"screen -r {screen_session}",
            "detach_keys": "Ctrl+A, D",
            "exists": ScreenManager.screen_exists(screen_session)
        }
    
    async def get_server_status(self, server_id: str) -> Optional[dict]:
        """서버 상태 조회 (mcstatus)"""
        try:
            config = self.get_server_config(server_id)
            if not config:
                return None
            
            server = JavaServer.lookup(f"localhost:{config['port']}")
            status = await asyncio.to_thread(server.status)
            
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
            
        except Exception as e:
            return {"online": False, "error": str(e)}
    
    async def cleanup_on_shutdown(self):
        """봇 종료 시 정리"""
        print("\n🧹 서버 정리 중...")
        
        for server_id in list(self.running_servers.keys()):
            config = self.get_server_config(server_id)
            print(f"   - {config['name']} 중지 중...")
            await self.stop_server(server_id, force=False)
        
        print("✅ 서버 정리 완료")
    async def get_server_performance(self, server_id: str) -> Optional[dict]:
        """서버 성능 정보 조회 (CPU, 메모리, 가동시간)"""
        try:
            obj = self.running_servers.get(server_id)
            if not obj:
                return None
            
            # Screen 세션인 경우 PID 찾기
            if isinstance(obj, str):
                # screen 세션에서 실행 중인 java 프로세스 찾기
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and 'java' in proc.info['name'].lower():
                            # 서버 경로가 포함되어 있는지 확인
                            config = self.get_server_config(server_id)
                            if config and config['path'] in ' '.join(cmdline):
                                pid = proc.info['pid']
                                process = psutil.Process(pid)
                                break
                    except:
                        continue
                else:
                    return None
            # Popen 프로세스인 경우
            elif isinstance(obj, subprocess.Popen):
                try:
                    process = psutil.Process(obj.pid)
                except:
                    return None
            else:
                return None
            
            # 성능 정보 수집
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # 전체 시스템 메모리 대비 비율
            memory_percent = process.memory_percent()
            
            # 스레드 수
            threads = process.num_threads()
            
            # 가동 시간
            create_time = process.create_time()
            uptime_seconds = psutil.boot_time() - create_time
            if uptime_seconds < 0:
                uptime_seconds = 0
            
            return {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "memory_percent": memory_percent,
                "threads": threads,
                "uptime_seconds": uptime_seconds
            }
            
        except Exception as e:
            print(f"⚠️ 성능 정보 조회 실패: {e}")
            return None
    
    def get_all_server_ids(self) -> list:
        """모든 서버 ID 목록 반환"""
        return list(self.servers_config.keys())
    
    async def restart_server(self, server_id: str) -> Tuple[bool, str]:
        """서버 재시작"""
        config = self.get_server_config(server_id)
        if not config:
            return False, f"서버를 찾을 수 없습니다: {server_id}"
        
        # 중지
        print(f"🔄 서버 재시작 중: {config['name']}")
        success, stop_msg = await self.stop_server(server_id, force=False)
        
        if not success:
            return False, f"중지 실패: {stop_msg}"
        
        # 대기
        await asyncio.sleep(3)
        
        # 시작
        success, start_msg = await self.start_server(server_id)
        
        if success:
            return True, f"{config['name']} 서버가 재시작되었습니다."
        else:
            return False, f"시작 실패: {start_msg}"