# modules/gcp/GCPController.py

"""
GCP 컨트롤러 클라이언트 - Discord 채널 기반 통신
경로: modules/gcp/GCPController.py
"""

import discord
import asyncio
from typing import Optional, Tuple


class GCPController:
    """Discord 채널을 통해 VPN 서버의 컨트롤러 봇과 통신"""
    
    def __init__(self, bot, control_channel_id: int, controller_bot_id: int):
        self.bot = bot
        self.control_channel_id = control_channel_id
        self.controller_bot_id = controller_bot_id
    
    def get_control_channel(self) -> discord.TextChannel:
        """제어 채널 가져오기"""
        channel = self.bot.get_channel(self.control_channel_id)
        if not channel:
            raise ValueError(f"제어 채널을 찾을 수 없습니다: {self.control_channel_id}")
        return channel
    
    async def send_shutdown_request(self, instance: str, reason: str = "자동 종료") -> Tuple[bool, str]:
        """GCP 인스턴스 중지 요청"""
        try:
            channel = self.get_control_channel()
            
            message = await channel.send(f"!gcp_shutdown {instance} {reason}")
            
            print(f"📤 GCP 중지 요청 전송: {instance}")
            
            # 응답 대기 (최대 60초)
            def check(m):
                return (
                    m.reference and 
                    m.reference.message_id == message.id and
                    m.author.id == self.controller_bot_id
                )
            
            try:
                response = await self.bot.wait_for('message', check=check, timeout=60.0)
                
                if "✅" in response.content:
                    print(f"✅ GCP 중지 성공")
                    return True, response.content
                else:
                    print(f"❌ GCP 중지 실패: {response.content}")
                    return False, response.content
                    
            except asyncio.TimeoutError:
                print("⏱️ GCP 중지 요청 타임아웃")
                return False, "⏱️ 컨트롤러 봇 응답 없음 (타임아웃)"
                
        except Exception as e:
            print(f"❌ GCP 중지 요청 오류: {e}")
            return False, f"❌ 오류 발생: {e}"
    
    async def send_start_request(self, instance: str) -> Tuple[bool, str]:
        """GCP 인스턴스 시작 요청"""
        try:
            channel = self.get_control_channel()
            
            message = await channel.send(f"!gcp_start {instance}")
            
            print(f"📤 GCP 시작 요청 전송: {instance}")
            
            # 응답 대기 (최대 120초 - 시작은 오래 걸릴 수 있음)
            def check(m):
                return (
                    m.reference and 
                    m.reference.message_id == message.id and
                    m.author.id == self.controller_bot_id
                )
            
            try:
                response = await self.bot.wait_for('message', check=check, timeout=120.0)
                
                if "✅" in response.content:
                    print(f"✅ GCP 시작 성공")
                    return True, response.content
                else:
                    print(f"❌ GCP 시작 실패: {response.content}")
                    return False, response.content
                    
            except asyncio.TimeoutError:
                print("⏱️ GCP 시작 요청 타임아웃")
                return False, "⏱️ 컨트롤러 봇 응답 없음 (타임아웃)"
                
        except Exception as e:
            print(f"❌ GCP 시작 요청 오류: {e}")
            return False, f"❌ 오류 발생: {e}"
    
    async def check_status(self, instance: str) -> Tuple[bool, str]:
        """GCP 인스턴스 상태 확인"""
        try:
            channel = self.get_control_channel()
            
            message = await channel.send(f"!gcp_status {instance}")
            
            def check(m):
                return (
                    m.reference and 
                    m.reference.message_id == message.id and
                    m.author.id == self.controller_bot_id
                )
            
            try:
                response = await self.bot.wait_for('message', check=check, timeout=15.0)
                
                # 상태 파싱
                content = response.content
                if "RUNNING" in content or "🟢" in content:
                    return True, content
                elif "TERMINATED" in content or "🔴" in content:
                    return True, content
                else:
                    return True, content
                    
            except asyncio.TimeoutError:
                return False, "⏱️ 응답 없음"
                
        except Exception as e:
            return False, f"❌ 오류: {e}"
    
    async def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            channel = self.get_control_channel()
            
            message = await channel.send("!ping")
            
            def check(m):
                return (
                    m.reference and 
                    m.reference.message_id == message.id and
                    m.author.id == self.controller_bot_id and
                    "Pong" in m.content
                )
            
            try:
                await self.bot.wait_for('message', check=check, timeout=10.0)
                print("✅ 컨트롤러 봇 연결 확인")
                return True
            except asyncio.TimeoutError:
                print("❌ 컨트롤러 봇 응답 없음")
                return False
                
        except Exception as e:
            print(f"❌ 연결 테스트 오류: {e}")
            return False