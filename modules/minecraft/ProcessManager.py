"""
서버 프로세스 실행·추적·재연결 (Windows 기본, terminal_mode="process")
경로: modules/minecraft/ProcessManager.py

- java 를 직접 실행 (run.bat 안 거침 → PID 가 곧 java)
  Windows: 새 콘솔 창(기본 최소화)으로 띄움 → 봇이 죽거나 봇 콘솔이 닫혀도 서버는 계속 돎
           CREATE_BREAKAWAY_FROM_JOB 도 시도 (서비스 래퍼가 봇의 프로세스 트리를 죽이는 경우 대비)
- PID 파일: <서버폴더>/<SERVER_STATE_DIRNAME>/process.json (임시 파일 → os.replace)
- 재연결 검증 (전부 통과해야 "같은 프로세스"):
    PID 존재 + 생성 시각 일치(±1초, 재부팅 후 PID 재사용 대비) + 실행 파일 일치 + 명령줄 일치
    (+ 작업 폴더 일치: 권한 문제로 못 읽으면 건너뜀)
- 봇이 켜지 않은 서버(run.bat 직접 실행 등)는 작업 폴더가 서버 폴더인 java 프로세스로 찾아서 "외부 실행"으로 등록
- Ctrl+C 전달: 별도 도우미 프로세스가 서버 콘솔에 붙어서 CTRL_C 이벤트를 보냄
  → JVM 종료 훅에서 마크 서버가 월드를 저장하고 꺼짐 (TerminateProcess 와 달리 저장됨)
"""

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import psutil

IS_WINDOWS = platform.system() == "Windows"

STATE_FILE_NAME = "process.json"
STATE_VERSION = 1
CREATE_TIME_TOLERANCE = 1.0  # 초

# Windows 창/프로세스 플래그
SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# 서버 콘솔에 붙어서 Ctrl+C 를 보내거나 창 제목을 바꾸는 도우미 (콘솔 없는 프로세스로 실행됨)
_CONSOLE_HELPER = r"""
import ctypes, sys
k = ctypes.WinDLL("kernel32", use_last_error=True)
action, pid = sys.argv[1], int(sys.argv[2])
k.FreeConsole()
if not k.AttachConsole(pid):
    sys.exit(2)
if action == "ctrlc":
    k.SetConsoleCtrlHandler(None, True)   # 나 자신은 무시
    ok = k.GenerateConsoleCtrlEvent(0, 0) # CTRL_C_EVENT → 이 콘솔의 모든 프로세스
    sys.exit(0 if ok else 3)
elif action == "title":
    k.SetConsoleTitleW(sys.argv[3])
    sys.exit(0)
"""


@dataclass
class TrackedProcess:
    server_id: str
    server_path: Path
    proc: psutil.Process
    record: dict
    external: bool = False          # 봇이 켜지 않은 서버
    popen: Optional[subprocess.Popen] = None

    @property
    def pid(self) -> int:
        return self.proc.pid


def _norm(path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class ProcessManager:
    def __init__(self, state_dirname: str = ".krangbot",
                 console_mode: str = "minimized",
                 adopt_names: Tuple[str, ...] = ("java.exe", "javaw.exe", "java")):
        self.state_dirname = state_dirname
        self.console_mode = console_mode
        self.adopt_names = tuple(n.lower() for n in adopt_names)
        self.tracked: Dict[str, TrackedProcess] = {}

    # ============================================
    # PID 파일
    # ============================================

    def state_file(self, server_path: Path) -> Path:
        return Path(server_path) / self.state_dirname / STATE_FILE_NAME

    def read_state(self, server_path: Path) -> Optional[dict]:
        f = self.state_file(server_path)
        if not f.exists():
            return None
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "pid" not in data or "create_time" not in data:
                raise ValueError("형식이 다름")
            return data
        except Exception as e:
            print(f"   ⚠️ PID 파일을 못 읽음 ({f}): {e} → 무시")
            self._discard_state(server_path, reason="corrupt")
            return None

    def _discard_state(self, server_path: Path, reason: str = "stale"):
        f = self.state_file(server_path)
        if f.exists():
            try:
                os.replace(f, f.with_name(f"{STATE_FILE_NAME}.{reason}"))
            except OSError:
                try:
                    f.unlink()
                except OSError:
                    pass

    def clear_state(self, server_path: Path):
        try:
            self.state_file(server_path).unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"   ⚠️ PID 파일 삭제 실패: {e}")

    # ============================================
    # 검증
    # ============================================

    @staticmethod
    def verify_record(record: dict, server_path: Optional[Path] = None) -> Tuple[Optional[psutil.Process], str]:
        """PID 파일 내용이 지금 살아 있는 '그' 프로세스인지 확인"""
        try:
            proc = psutil.Process(int(record["pid"]))
        except (psutil.NoSuchProcess, ValueError, TypeError, KeyError):
            return None, "프로세스 없음"
        except psutil.AccessDenied:
            return None, "프로세스 접근 거부"
        try:
            if proc.status() == psutil.STATUS_ZOMBIE:
                return None, "이미 종료됨(좀비)"
            if abs(proc.create_time() - float(record["create_time"])) > CREATE_TIME_TOLERANCE:
                return None, "PID 가 다른 프로세스에 재사용됨 (생성 시각 다름)"
            checked = 0
            try:
                if record.get("exe"):
                    if _norm(proc.exe()) != _norm(record["exe"]):
                        return None, "실행 파일이 다름"
                    checked += 1
            except psutil.AccessDenied:
                pass
            try:
                if record.get("cmdline"):
                    if proc.cmdline() != record["cmdline"]:
                        return None, "명령줄이 다름"
                    checked += 1
            except psutil.AccessDenied:
                pass
            if checked == 0:
                return None, "실행 파일·명령줄을 확인할 수 없음"
            if server_path is not None:
                try:
                    if _norm(proc.cwd()) != _norm(server_path):
                        return None, "작업 폴더가 다름"
                except psutil.AccessDenied:
                    pass
        except psutil.NoSuchProcess:
            return None, "프로세스 없음"
        return proc, "OK"

    # ============================================
    # 실행
    # ============================================

    def launch(self, server_id: str, server_path: Path, argv: List[str], extra: Optional[dict] = None,
               title: Optional[str] = None) -> Tuple[bool, str, Optional[TrackedProcess]]:
        """
        서버 프로세스 실행 + PID 파일 기록. 시작 성공 여부(죽지 않고 버티는지)는 호출 쪽에서 확인.
        """
        server_path = Path(server_path)
        kwargs = dict(cwd=str(server_path), close_fds=True)

        if IS_WINDOWS:
            import ctypes
            # 봇이 "Ctrl+C 무시" 상태로 실행됐으면 자식이 그걸 물려받아 Ctrl+C 로 못 끄게 됨 → 해제
            try:
                ctypes.WinDLL("kernel32").SetConsoleCtrlHandler(None, False)
            except Exception:
                pass
            mode = self.console_mode
            if mode == "hidden":
                flags = subprocess.CREATE_NO_WINDOW
                si = None
            else:
                flags = subprocess.CREATE_NEW_CONSOLE
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = SW_SHOWNOACTIVATE if mode == "normal" else SW_SHOWMINNOACTIVE
            kwargs["startupinfo"] = si
            try:
                popen = subprocess.Popen(argv, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kwargs)
            except OSError as e:
                # 작업 개체(Job)가 분리를 허용하지 않으면 실패함 → 분리 없이 실행
                if getattr(e, "winerror", None) != 5:
                    raise
                print("   ℹ️ 작업 개체 분리 불가 → 일반 실행 (봇을 감싼 프로그램이 트리를 죽이면 서버도 꺼질 수 있음)")
                popen = subprocess.Popen(argv, creationflags=flags, **kwargs)
        else:
            state_dir = server_path / self.state_dirname
            state_dir.mkdir(parents=True, exist_ok=True)
            log = open(state_dir / "console.log", "ab")
            try:
                popen = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True, **kwargs)
            finally:
                log.close()

        try:
            proc = psutil.Process(popen.pid)
            create_time = proc.create_time()
            try:
                exe = proc.exe()
            except psutil.AccessDenied:
                exe = None
            try:
                cmdline = proc.cmdline()
            except psutil.AccessDenied:
                cmdline = None
        except psutil.NoSuchProcess:
            return False, "프로세스가 시작하자마자 종료됐습니다", None

        record = {
            "version": STATE_VERSION,
            "server_id": server_id,
            "pid": popen.pid,
            "create_time": create_time,
            "exe": exe,
            "cmdline": cmdline,
            "cwd": str(server_path),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "console_mode": self.console_mode if IS_WINDOWS else "log",
            "external": False,
        }
        record.update(extra or {})
        try:
            _atomic_write_json(self.state_file(server_path), record)
        except OSError as e:
            print(f"   ⚠️ PID 파일 기록 실패 (봇 재시작 시 재연결이 안 될 수 있음): {e}")

        tracked = TrackedProcess(server_id, server_path, proc, record, popen=popen)
        self.tracked[server_id] = tracked

        if title and IS_WINDOWS and self.console_mode != "hidden":
            self._run_console_helper("title", popen.pid, title, wait=False)

        return True, f"PID {popen.pid}", tracked

    # ============================================
    # 찾기 / 재연결
    # ============================================

    def find_running(self, server_id: str, server_path: Path, adopt_external: bool = True) -> Optional[TrackedProcess]:
        """이미 추적 중이거나, PID 파일로 재연결되거나, 외부에서 켠 서버면 TrackedProcess"""
        server_path = Path(server_path)
        t = self.tracked.get(server_id)
        if t is not None:
            if self._alive(t):
                return t
            self.forget(server_id, clear_file=True)

        record = self.read_state(server_path)
        if record:
            proc, why = self.verify_record(record, server_path)
            if proc:
                t = TrackedProcess(server_id, server_path, proc, record, external=bool(record.get("external")))
                self.tracked[server_id] = t
                return t
            print(f"   🧹 [{server_id}] 이전 PID 파일 무효 ({why}) → 정리")
            self._discard_state(server_path)

        if adopt_external:
            proc = self._find_by_cwd(server_path)
            if proc:
                try:
                    record = {
                        "version": STATE_VERSION, "server_id": server_id, "pid": proc.pid,
                        "create_time": proc.create_time(), "exe": proc.exe(), "cmdline": proc.cmdline(),
                        "cwd": str(server_path), "started_at": None, "external": True,
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return None
                try:
                    _atomic_write_json(self.state_file(server_path), record)
                except OSError:
                    pass
                t = TrackedProcess(server_id, server_path, proc, record, external=True)
                self.tracked[server_id] = t
                print(f"   🔗 [{server_id}] 봇 밖에서 켠 서버 발견 (PID {proc.pid}) → 외부 실행으로 등록")
                return t
        return None

    def _find_by_cwd(self, server_path: Path) -> Optional[psutil.Process]:
        target = _norm(server_path)
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info.get("name") or "").lower() not in self.adopt_names:
                    continue
                if _norm(p.cwd()) == target:
                    return p
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        return None

    def _alive(self, t: TrackedProcess) -> bool:
        if t.popen is not None and t.popen.poll() is not None:
            return False
        try:
            return t.proc.is_running() and t.proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def is_alive(self, server_id: str) -> bool:
        t = self.tracked.get(server_id)
        if t is None:
            return False
        if self._alive(t):
            return True
        print(f"   💤 [{server_id}] 서버 프로세스 종료 확인 (PID {t.pid})")
        self.forget(server_id, clear_file=True)
        return False

    def get(self, server_id: str) -> Optional[TrackedProcess]:
        return self.tracked.get(server_id) if self.is_alive(server_id) else None

    def forget(self, server_id: str, clear_file: bool = True):
        t = self.tracked.pop(server_id, None)
        if t and clear_file:
            # 다른 프로세스 기록으로 바뀌었으면 지우지 않음
            rec = self.read_state(t.server_path) if self.state_file(t.server_path).exists() else None
            if rec is None or rec.get("pid") == t.pid:
                self.clear_state(t.server_path)
        if t and t.popen is not None:
            try:
                t.popen.poll()
            except Exception:
                pass

    # ============================================
    # 종료
    # ============================================

    def _run_console_helper(self, action: str, pid: int, *extra: str, wait: bool = True) -> bool:
        if not IS_WINDOWS:
            return False
        cmd = [sys.executable, "-I", "-c", _CONSOLE_HELPER, action, str(pid), *extra]
        try:
            p = subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True)
            if not wait:
                return True
            return p.wait(timeout=15) == 0
        except Exception as e:
            print(f"   ⚠️ 콘솔 도우미 실패 ({action}): {e}")
            return False

    def send_ctrl_c(self, server_id: str) -> bool:
        """서버 콘솔에 Ctrl+C → JVM 종료 훅에서 월드 저장 후 종료"""
        t = self.tracked.get(server_id)
        if t is None:
            return False
        if IS_WINDOWS:
            return self._run_console_helper("ctrlc", t.pid)
        try:
            import signal
            os.kill(t.pid, signal.SIGINT)
            return True
        except OSError:
            return False

    def kill(self, server_id: str) -> bool:
        """즉시 강제 종료 (저장 안 됨)"""
        t = self.tracked.get(server_id)
        if t is None:
            return False
        try:
            t.proc.kill()
            return True
        except psutil.NoSuchProcess:
            return True
        except psutil.AccessDenied:
            return False

    def wait_exit(self, server_id: str, timeout: float) -> bool:
        """동기 대기 (스레드에서 호출). 종료되면 True"""
        t = self.tracked.get(server_id)
        if t is None:
            return True
        try:
            t.proc.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            return False
        except psutil.NoSuchProcess:
            return True

    def uptime_seconds(self, server_id: str) -> Optional[float]:
        t = self.tracked.get(server_id)
        if t is None:
            return None
        try:
            return time.time() - t.proc.create_time()
        except psutil.NoSuchProcess:
            return None
