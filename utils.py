"""
유틸리티 함수 모음
경로: utils.py
"""

import discord
from config import BOT_OWNER_ID


def is_authorized(user: discord.User, required_permission: str = "manage_guild") -> bool:
    """
    사용자 권한 확인
    
    Args:
        user: Discord 사용자
        required_permission: 필요한 권한
            - "administrator": 관리자 권한
            - "manage_guild": 서버 관리 권한
            - "manage_channels": 채널 관리 권한
    
    Returns:
        권한이 있으면 True
    """
    # 봇 소유자는 항상 권한 있음
    if user.id == BOT_OWNER_ID:
        return True
    
    # Member 객체가 아니면 권한 확인 불가
    if not isinstance(user, discord.Member):
        return False
    
    # 권한 확인
    if required_permission == "administrator":
        return user.guild_permissions.administrator
    elif required_permission == "manage_guild":
        return user.guild_permissions.manage_guild or user.guild_permissions.administrator
    elif required_permission == "manage_channels":
        return user.guild_permissions.manage_channels or user.guild_permissions.administrator
    
    # 알 수 없는 권한은 거부
    return False