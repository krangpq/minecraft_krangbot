"""
Screen 세션을 사용한 마인크래프트 서버 관리
Linux 전용 - SSH 환경에 최적화
"""

import subprocess
import asyncio
import platform
from pathlib import Path
from typing import Optional, Tuple, List


class ScreenManager:
    """Screen 세션 관리"""
    
    @staticmethod
    def is_screen_available() -> bool:
        """screen 명령어가 설치되어 있는지 확인"""
        try:
            subprocess.run(['screen', '-v'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    @staticmethod
    def list_screens(filter_prefix: str = None) -> List[str]:
        """
        실행 중인 모든 screen 세션 목록
        
        Args:
            filter_prefix: 세션 이름 필터 (예: "minecraft_")
        """
        try:
            result = subprocess.run(
                ['screen', '-ls'],
                capture_output=True,
                text=True
            )
            
            # 출력 파싱
            lines = result.stdout.split('\n')
            screens = []
            
            for line in lines:
                # 공백/탭 정리
                line = line.strip()
                
                # 빈 줄이나 헤더 라인 건너뛰기
                if not line:
                    continue
                if line.startswith('There'):
                    continue
                if line.startswith('No Sockets'):
                    continue
                if 'Socket' in line and 'in' in line:
                    continue
                
                # 세션 라인 감지: "PID.name (상태)" 형식
                if '.' in line and '(' in line:
                    parts = line.split()
                    if parts:
                        session_id = parts[0]
                        if '.' in session_id:
                            pid_part = session_id.split('.')[0]
                            name_part = session_id.split('.', 1)[1]
                            
                            if pid_part.isdigit():
                                # 필터링
                                if filter_prefix:
                                    if name_part.startswith(filter_prefix):
                                        screens.append(session_id)
                                else:
                                    screens.append(session_id)
            
            return screens
            
        except Exception as e:
            print(f"⚠️ screen 목록 조회 실패: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def screen_exists(session_name: str) -> bool:
        """특정 screen 세션이 존재하는지 확인 (PID 무시)"""
        return ScreenManager.find_screen_by_name(session_name) is not None
    
    @staticmethod
    async def create_screen(session_name: str, command: str, cwd: str, reuse_existing: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        새 screen 세션 생성 및 명령어 실행 (개선된 버전)
        
        Args:
            session_name: screen 세션 이름
            command: 실행할 명령어
            cwd: 작업 디렉토리
            reuse_existing: 기존 세션 재사용 여부
        
        Returns:
            (성공 여부, 메시지, 실제 세션 ID)
        """
        try:
            print(f"   🔍 Screen 세션 생성 시작")
            print(f"      요청 세션명: {session_name}")
            print(f"      작업 디렉토리: {cwd}")
            
            # 기존 세션 확인
            existing_session = ScreenManager.find_screen_by_name(session_name)
            
            if existing_session:
                if reuse_existing:
                    print(f"   ⚠️ 기존 Screen 세션 발견: {existing_session}")
                    print(f"      기존 세션을 종료하고 새로 시작합니다...")
                    
                    # 기존 세션 강제 종료
                    await ScreenManager.kill_screen(existing_session)
                    
                    # 종료 확인 (최대 5초 대기)
                    for i in range(10):
                        await asyncio.sleep(0.5)
                        if not ScreenManager.screen_exists(session_name):
                            print(f"      ✅ 기존 세션 종료 완료")
                            break
                        if i == 9:
                            print(f"      ⚠️ 기존 세션 종료 확인 실패, 계속 진행...")
                    
                    # 추가 대기 (안전성)
                    await asyncio.sleep(2)
                else:
                    return False, f"Screen 세션이 이미 존재합니다: {existing_session}", None
            
            # screen 세션 생성 및 명령어 실행
            screen_command = [
                'screen',
                '-dmS', session_name,
                'bash', '-c',
                f'cd "{cwd}" && {command}'
            ]
            
            print(f"      실행 명령: {' '.join(screen_command[:4])}...")
            
            process = await asyncio.create_subprocess_exec(
                *screen_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # ✅ screen 명령어 실행 결과 확인
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "알 수 없는 오류"
                print(f"      ❌ screen 명령어 실행 실패 (코드 {process.returncode})")
                print(f"      stderr: {error_msg}")
                return False, f"Screen 명령어 실행 실패: {error_msg}", None
            
            if stdout:
                print(f"      stdout: {stdout.decode()}")
            if stderr:
                print(f"      stderr: {stderr.decode()}")
            
            # ✅ 세션 생성 확인 (최대 10초 대기, 0.5초 간격으로 20번 확인)
            print(f"      ⏳ Screen 세션 등록 확인 중...")
            actual_session = None
            
            for i in range(20):
                await asyncio.sleep(0.5)
                actual_session = ScreenManager.find_screen_by_name(session_name)
                
                if actual_session:
                    print(f"      ✅ 세션 확인됨: {actual_session} (시도 {i+1}/20)")
                    return True, f"Screen 세션 생성 완료: {actual_session}", actual_session
                else:
                    if i == 0 or i == 9 or i == 19:  # 처음, 중간, 마지막만 출력
                        print(f"      ⏳ 대기 중... (시도 {i+1}/20)")
            
            # 최종 확인
            all_screens = ScreenManager.list_screens()
            print(f"      ❌ 세션을 찾을 수 없습니다")
            print(f"      현재 모든 Screen 세션: {all_screens}")
            
            return False, "Screen 세션 생성 실패: 세션을 찾을 수 없음", None
            
        except Exception as e:
            print(f"   ❌ Screen 생성 오류: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Screen 생성 오류: {e}", None
    
    @staticmethod
    async def send_to_screen(session_name: str, command: str) -> Tuple[bool, str]:
        """
        실행 중인 screen 세션에 명령어 전송
        
        Args:
            session_name: screen 세션 이름
            command: 전송할 명령어
        
        Returns:
            (성공 여부, 메시지)
        """
        try:
            # 실제 세션 ID 찾기 (PID 포함)
            actual_session = ScreenManager.find_screen_by_name(session_name)
            
            if not actual_session:
                return False, f"Screen 세션을 찾을 수 없습니다: {session_name}"
            
            # screen -S session_id -X stuff "command\n"
            screen_command = [
                'screen',
                '-S', actual_session,  # 실제 세션 ID 사용
                '-X', 'stuff',
                f'{command}\n'
            ]
            
            process = await asyncio.create_subprocess_exec(
                *screen_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.wait()
            
            return True, f"명령어 전송 완료: {command}"
            
        except Exception as e:
            return False, f"명령어 전송 오류: {e}"
    
    @staticmethod
    async def kill_screen(session_name: str) -> Tuple[bool, str]:
        """
        screen 세션 종료
        
        Args:
            session_name: screen 세션 이름
        
        Returns:
            (성공 여부, 메시지)
        """
        try:
            # 실제 세션 ID 찾기
            actual_session = ScreenManager.find_screen_by_name(session_name)
            
            if not actual_session:
                return False, f"Screen 세션을 찾을 수 없습니다: {session_name}"
            
            # screen -S session_id -X quit
            screen_command = ['screen', '-S', actual_session, '-X', 'quit']
            
            process = await asyncio.create_subprocess_exec(
                *screen_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.wait()
            
            # 종료 확인
            await asyncio.sleep(1)
            if not ScreenManager.screen_exists(session_name):
                return True, f"Screen 세션 종료 완료: {actual_session}"
            else:
                return False, "Screen 세션 종료 실패"
            
        except Exception as e:
            return False, f"Screen 종료 오류: {e}"
    
    @staticmethod
    def get_attach_command(session_name: str) -> str:
        """
        Screen 세션에 접속하는 명령어 반환
        
        Returns:
            "screen -r session_name" 명령어 문자열
        """
        return f"screen -r {session_name}"
    
    @staticmethod
    def find_screen_by_name(session_name: str) -> Optional[str]:
        """
        Screen 세션을 이름으로 찾기 (PID.name 형식 처리)
        
        Args:
            session_name: 찾을 세션 이름 (예: "minecraft_testserver")
        
        Returns:
            전체 세션 ID (예: "12345.minecraft_main") 또는 None
        """
        # ✅ minecraft_로 시작하는 세션만 검색
        if "_" in session_name:
            # "minecraft_testserver" -> "minecraft_"
            # "spigot_build_1_21_1" -> "spigot_build_"
            if session_name.startswith("spigot_build_"):
                filter_prefix = "spigot_build_"
            elif session_name.startswith("minecraft_"):
                filter_prefix = "minecraft_"
            else:
                filter_prefix = None
        else:
            filter_prefix = None
        
        screens = ScreenManager.list_screens(filter_prefix=filter_prefix)
        
        for screen in screens:
            # "12345.minecraft_main" 형식에서 이름 부분만 추출
            if '.' in screen:
                # 점을 기준으로 나누되, 첫 번째만 PID로 간주 (나머지는 세션명)
                parts = screen.split('.', 1)
                if len(parts) == 2:
                    # PID는 숫자여야 함
                    pid_part = parts[0]
                    name_part = parts[1]
                    
                    # PID가 숫자인지 확인
                    if pid_part.isdigit() and name_part == session_name:
                        return screen
            
            # 점이 없는 경우 (드물지만 가능)
            if screen == session_name:
                return screen
        
        return None


class TerminalLauncher:
    """OS별 터미널 실행기 (Screen 통합)"""
    
    def __init__(self):
        self.os_type = platform.system()
        self.screen_manager = ScreenManager()
    
    async def launch_server(
        self,
        server_id: str,
        command: str,
        cwd: str,
        use_screen: bool = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        서버 시작 (OS별 자동 선택)
        
        Args:
            server_id: 서버 ID
            command: 실행 명령어
            cwd: 작업 디렉토리
            use_screen: Screen 사용 여부 (Linux만 해당)
                - None: OS에 따라 자동
                - True: 강제로 Screen 사용
                - False: 강제로 백그라운드
        
        Returns:
            (성공 여부, 메시지, screen 세션명 또는 None)
        """
        # Linux + Screen 사용
        if self.os_type == "Linux":
            if use_screen is None or use_screen:
                if self.screen_manager.is_screen_available():
                    return await self._launch_linux_screen(server_id, command, cwd)
                else:
                    print("⚠️ screen이 설치되지 않았습니다. 백그라운드 모드로 실행합니다.")
                    print("   설치: sudo apt install screen")
            
            # Screen 사용 안 함 또는 설치 안 됨
            return await self._launch_background(command, cwd)
        
        # Windows
        elif self.os_type == "Windows":
            return await self._launch_windows(server_id, command, cwd, use_screen)
        
        # macOS
        elif self.os_type == "Darwin":
            return await self._launch_macos(server_id, command, cwd, use_screen)
        
        else:
            return False, f"지원하지 않는 OS: {self.os_type}", None
    
    async def _launch_linux_screen(
        self,
        server_id: str,
        command: str,
        cwd: str
    ) -> Tuple[bool, str, str]:
        """Linux: Screen 세션에서 서버 시작"""
        session_name = f"minecraft_{server_id}"
        
        print(f"   🖥️ Screen 세션 생성 중: {session_name}")
        
        success, message, actual_session = await self.screen_manager.create_screen(
            session_name=session_name,
            command=command,
            cwd=cwd,
            reuse_existing=True  # ✅ 기존 세션 재사용
        )
        
        if success:
            attach_cmd = self.screen_manager.get_attach_command(session_name)
            full_message = (
                f"{message}\n"
                f"💡 콘솔 접속: `{attach_cmd}`\n"
                f"💡 나가기: Ctrl+A, D"
            )
            return True, full_message, actual_session or session_name
        else:
            return False, message, None
    
    async def _launch_background(
        self,
        command: str,
        cwd: str
    ) -> Tuple[bool, str, None]:
        """백그라운드 모드로 서버 시작"""
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE
            )
            
            await asyncio.sleep(2)
            
            if process.poll() is None:
                return True, "서버가 백그라운드에서 시작되었습니다.", None
            else:
                return False, "서버 시작에 실패했습니다.", None
                
        except Exception as e:
            return False, f"오류: {e}", None
    
    async def _launch_windows(
        self,
        server_id: str,
        command: str,
        cwd: str,
        use_separate: bool
    ) -> Tuple[bool, str, None]:
        """Windows: cmd 또는 백그라운드"""
        if use_separate:
            # 새 cmd 창
            title = f"Minecraft - {server_id}"
            full_command = f'start "{title}" cmd /k "cd /d {cwd} && {command}"'
            
            subprocess.Popen(
                full_command,
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            await asyncio.sleep(2)
            return True, f"서버가 새 콘솔 창에서 시작되었습니다. (제목: {title})", None
        else:
            # 백그라운드
            return await self._launch_background(command, cwd)
    
    async def _launch_macos(
        self,
        server_id: str,
        command: str,
        cwd: str,
        use_separate: bool
    ) -> Tuple[bool, str, None]:
        """macOS: Terminal.app 또는 백그라운드"""
        if use_separate:
            # 새 Terminal 창
            title = f"Minecraft - {server_id}"
            applescript = f'''
            tell application "Terminal"
                do script "cd '{cwd}' && {command}"
                set custom title of front window to "{title}"
                activate
            end tell
            '''
            
            subprocess.Popen(['osascript', '-e', applescript])
            
            await asyncio.sleep(2)
            return True, f"서버가 새 터미널 창에서 시작되었습니다.", None
        else:
            # 백그라운드
            return await self._launch_background(command, cwd)
    
    async def send_command(
        self,
        server_id: str,
        command: str,
        screen_session: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        서버에 명령어 전송
        
        Args:
            server_id: 서버 ID
            command: 명령어
            screen_session: Screen 세션명 (Linux)
        
        Returns:
            (성공 여부, 메시지)
        """
        if self.os_type == "Linux" and screen_session:
            # Screen에 명령어 전송
            return await self.screen_manager.send_to_screen(screen_session, command)
        else:
            # stdin으로 전송 (기존 방식)
            return False, "stdin 전송은 ServerManager에서 처리"