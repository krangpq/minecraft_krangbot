"""
RCON 클라이언트 - 마인크래프트 서버와 통신
경로: modules/minecraft/RconClient.py

mcrcon 라이브러리 대신 직접 구현:
  - mcrcon 은 Windows 에서 응답 대기 시간 제한이 없어서, 서버가 멈추면 봇 스레드도 같이 멈춤
  - Linux 에서는 SIGALRM 을 써서 asyncio.to_thread(다른 스레드) 안에서 쓰면 오류
RCON 프로토콜: 패킷 = <길이 int32><id int32><종류 int32><본문 UTF-8>\x00\x00 (리틀 엔디언)
  종류 3 = 로그인, 2 = 명령, 0 = 응답. 로그인 실패 시 응답 id 가 -1.
"""

import asyncio
import socket
import struct
from typing import Tuple

TYPE_LOGIN = 3
TYPE_COMMAND = 2
TYPE_RESPONSE = 0


class RconError(Exception):
    pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise RconError("서버가 연결을 끊었습니다")
        data += chunk
    return data


def _send_packet(sock: socket.socket, req_id: int, ptype: int, body: str):
    payload = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
    sock.sendall(struct.pack("<i", len(payload)) + payload)


def _recv_packet(sock: socket.socket) -> Tuple[int, int, str]:
    (length,) = struct.unpack("<i", _recv_exact(sock, 4))
    if length < 10 or length > 1024 * 1024:
        raise RconError(f"이상한 RCON 패킷 길이: {length}")
    data = _recv_exact(sock, length)
    req_id, ptype = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return req_id, ptype, body


def rcon_command(host: str, port: int, password: str, command: str, timeout: float = 5.0) -> str:
    """동기 RCON 명령 1개 (연결 → 로그인 → 명령 → 응답 → 끊기)"""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        _send_packet(sock, 1, TYPE_LOGIN, password)
        req_id, _, _ = _recv_packet(sock)
        if req_id == -1:
            raise RconError("RCON 비밀번호가 틀렸습니다")
        _send_packet(sock, 2, TYPE_COMMAND, command)
        _, _, body = _recv_packet(sock)
        return body


class RconClient:
    """RCON을 통한 마인크래프트 서버 명령어 실행"""

    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    async def execute_command(self, command: str) -> Tuple[bool, str]:
        """
        RCON으로 명령어 실행 및 결과 반환

        Returns:
            (성공 여부, 결과 메시지)
        """
        try:
            result = await asyncio.to_thread(self._execute_sync, command)
            return True, result
        except Exception as e:
            return False, f"RCON 오류: {e}"

    def _execute_sync(self, command: str) -> str:
        return rcon_command(self.host, self.port, self.password, command, self.timeout)

    async def send_stop(self) -> Tuple[bool, str]:
        """
        stop 전송. 서버가 응답 전에 연결을 끊는 경우가 있어서,
        로그인까지 되고 명령을 보낸 뒤 끊기면 '보냄'으로 봄 (실제 종료는 프로세스로 확인)
        """
        def _do():
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                _send_packet(sock, 1, TYPE_LOGIN, self.password)
                req_id, _, _ = _recv_packet(sock)
                if req_id == -1:
                    raise RconError("RCON 비밀번호가 틀렸습니다")
                _send_packet(sock, 2, TYPE_COMMAND, "stop")
                try:
                    _, _, body = _recv_packet(sock)
                    return body
                except (RconError, OSError):
                    return ""
        try:
            return True, await asyncio.to_thread(_do)
        except Exception as e:
            return False, f"RCON 오류: {e}"

    async def get_player_list(self) -> Tuple[bool, list]:
        """플레이어 목록 가져오기"""
        success, response = await self.execute_command("list")

        if not success:
            return False, []

        # "There are 3/20 players online: Player1, Player2, Player3" 파싱
        try:
            if ":" in response:
                players_str = response.split(":")[1].strip()
                if players_str:
                    players = [p.strip() for p in players_str.split(",")]
                    return True, players
            return True, []
        except Exception:
            return False, []

    async def say(self, message: str) -> Tuple[bool, str]:
        """서버에 메시지 브로드캐스트"""
        return await self.execute_command(f"say {message}")

    async def kick_player(self, player_name: str, reason: str = "") -> Tuple[bool, str]:
        """플레이어 킥"""
        cmd = f"kick {player_name}"
        if reason:
            cmd += f" {reason}"
        return await self.execute_command(cmd)

    async def whitelist_add(self, player_name: str) -> Tuple[bool, str]:
        """화이트리스트에 플레이어 추가"""
        return await self.execute_command(f"whitelist add {player_name}")

    async def whitelist_remove(self, player_name: str) -> Tuple[bool, str]:
        """화이트리스트에서 플레이어 제거"""
        return await self.execute_command(f"whitelist remove {player_name}")

    async def save_all(self, flush: bool = False) -> Tuple[bool, str]:
        """월드 저장 (flush=True 면 디스크에 다 쓸 때까지 기다림)"""
        return await self.execute_command("save-all flush" if flush else "save-all")

    async def test_connection(self) -> bool:
        """RCON 연결 테스트"""
        success, _ = await self.execute_command("list")
        return success
