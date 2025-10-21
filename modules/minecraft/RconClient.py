"""
RCON 클라이언트 - 마인크래프트 서버와 통신
경로: modules/minecraft/RconClient.py
"""

from mcrcon import MCRcon
import asyncio
from typing import Optional, Tuple


class RconClient:
    """RCON을 통한 마인크래프트 서버 명령어 실행"""
    
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
    
    async def execute_command(self, command: str) -> Tuple[bool, str]:
        """
        RCON으로 명령어 실행 및 결과 반환
        
        Args:
            command: 실행할 명령어
        
        Returns:
            (성공 여부, 결과 메시지)
        """
        try:
            # 비동기로 RCON 연결 및 실행
            result = await asyncio.to_thread(self._execute_sync, command)
            return True, result
        except Exception as e:
            return False, f"RCON 오류: {e}"
    
    def _execute_sync(self, command: str) -> str:
        """동기 방식의 RCON 실행 (내부용)"""
        with MCRcon(self.host, self.password, port=self.port) as mcr:
            response = mcr.command(command)
            return response
    
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
        except:
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
    
    async def save_all(self) -> Tuple[bool, str]:
        """월드 저장"""
        return await self.execute_command("save-all")
    
    async def test_connection(self) -> bool:
        """RCON 연결 테스트"""
        success, _ = await self.execute_command("list")
        return success