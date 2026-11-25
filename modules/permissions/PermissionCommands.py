"""
권한 관리 슬래시 명령어
경로: modules/permissions/PermissionCommands.py

/권한 부여  대상 등급   (관리자↑, 자기보다 낮은 등급까지)
/권한 회수  대상        (관리자↑)
/권한 목록              (관리자↑)
/내권한                 (누구나)
"""

import discord
from discord import app_commands

from .PermissionManager import GRANTABLE_LEVELS
from .PermissionTable import Level, level_label
from .PermissionTree import usable_commands

LEVEL_HINTS = {
    Level.MEMBER: "조회",
    Level.OPERATOR: "켜기·끄기·재시작·백업",
    Level.ADMIN: "콘솔 명령·서버 구성·권한 관리",
}

EMBED_FIELD_LIMIT = 1024


def _clip(text: str, limit: int = EMBED_FIELD_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 2] + "\n…"


def setup_permission_commands(bot):
    """권한 관리 명령어 등록 (bot.permissions 필요)"""

    group = app_commands.Group(name="권한", description="봇 명령어 권한(화이트리스트) 관리")

    level_choices = [
        app_commands.Choice(name=f"{level_label(lv)} ({LEVEL_HINTS[lv]})", value=int(lv))
        for lv in GRANTABLE_LEVELS
    ]

    @group.command(name="부여", description="유저를 화이트리스트에 넣거나 등급을 바꿉니다")
    @app_commands.describe(대상="권한을 줄 유저", 등급="부여할 등급")
    @app_commands.choices(등급=level_choices)
    async def grant(
        interaction: discord.Interaction,
        대상: discord.User,
        등급: app_commands.Choice[int],
    ):
        ok, message = bot.permissions.grant(interaction.user, 대상, Level(등급.value))
        await interaction.response.send_message(
            ("✅ " if ok else "❌ ") + message, ephemeral=True
        )

    @group.command(name="회수", description="유저를 화이트리스트에서 뺍니다")
    @app_commands.describe(대상="권한을 회수할 유저")
    async def revoke(interaction: discord.Interaction, 대상: discord.User):
        ok, message = bot.permissions.revoke(interaction.user, 대상)
        await interaction.response.send_message(
            ("✅ " if ok else "❌ ") + message, ephemeral=True
        )

    @group.command(name="목록", description="화이트리스트를 등급별로 봅니다")
    async def list_permissions(interaction: discord.Interaction):
        entries = bot.permissions.list_entries()
        embed = discord.Embed(title="🔐 권한 목록", color=discord.Color.blurple())
        embed.add_field(
            name=level_label(Level.OWNER),
            value=f"<@{bot.permissions.owner_id}>",
            inline=False,
        )
        for lv in sorted(GRANTABLE_LEVELS, reverse=True):
            members = [
                f"<@{uid}> ({entry.get('name', '?')})"
                for uid, entry in entries
                if entry["level"] == int(lv)
            ]
            embed.add_field(
                name=f"{level_label(lv)} ({len(members)}명)",
                value=_clip("\n".join(members)) if members else "없음",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    bot.tree.add_command(group)

    @bot.tree.command(name="내권한", description="내 권한 등급과 쓸 수 있는 명령어를 확인합니다")
    async def my_permission(interaction: discord.Interaction):
        level = bot.permissions.get_level(interaction.user)
        usable = usable_commands(bot.tree, level)
        lines = [f"🔐 내 등급: **{level_label(level)}**"]
        if level == Level.GUEST:
            lines.append("화이트리스트에 등록돼 있지 않아요. 관리자에게 등록을 요청하세요.")
        lines.append("")
        lines.append("쓸 수 있는 명령어: " + (", ".join(f"`/{n}`" for n in usable) or "없음"))
        await interaction.response.send_message(_clip("\n".join(lines), 2000), ephemeral=True)
