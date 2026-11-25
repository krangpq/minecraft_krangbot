"""
모든 슬래시 명령어 앞단의 권한 게이트
경로: modules/permissions/PermissionTree.py

commands.Bot(tree_cls=PermissionTree) 로 쓰면, 명령어 본문이 실행되기 전에
PermissionTable 의 표대로 등급을 검사합니다. 명령어 코드 안에서 권한을 따로 확인할 필요 없음.
자동완성도 같은 기준으로 막혀서, 권한 없는 사람에게 서버 이름 같은 게 노출되지 않습니다.
"""

from typing import Dict, List, Set

import discord
from discord import app_commands

from .PermissionTable import (
    COMMAND_LEVELS,
    DEFAULT_LEVEL,
    OPTION_LEVELS,
    Level,
    josa,
    level_label,
    requirement,
    resolve_command_path,
)


class InsufficientLevel(app_commands.CheckFailure):
    """권한 부족 (on_error 에서 안내 메시지로 바뀜)"""

    def __init__(self, command_name: str, required: Level, current: Level, option: str = None):
        self.command_name = command_name
        self.required = required
        self.current = current
        self.option = option
        super().__init__(
            f"/{command_name}: requires {required.name}, user has {current.name}"
            + (f" (option {option})" if option else "")
        )


async def _send_ephemeral(interaction: discord.Interaction, content: str):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)
    except discord.HTTPException:
        pass


class PermissionTree(app_commands.CommandTree):

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.type not in (
            discord.InteractionType.application_command,
            discord.InteractionType.autocomplete,
        ):
            return True

        name, options = resolve_command_path(interaction.data or {})
        needed, raised_by = requirement(name, options)
        if needed <= Level.GUEST:
            return True

        manager = getattr(self.client, "permissions", None)
        # 권한 관리자가 없으면 전부 막음 (안전한 쪽으로 실패)
        current = manager.get_level(interaction.user) if manager else Level.GUEST
        if current >= needed:
            return True

        if interaction.type is discord.InteractionType.autocomplete:
            # 자동완성은 메시지를 못 보내니 빈 목록으로 조용히 막음
            try:
                await interaction.response.autocomplete([])
            except discord.HTTPException:
                pass
            return False

        raise InsufficientLevel(name, needed, current, raised_by)

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(original, InsufficientLevel):
            required = level_label(original.required)
            if original.option:
                head = (
                    f"🔒 `/{original.command_name}` 의 `{original.option}` 옵션은 "
                    f"**{required}** 이상만 쓸 수 있어요."
                )
            else:
                head = f"🔒 `/{original.command_name}` 은(는) **{required}** 이상만 쓸 수 있어요."
            tail = f"(내 등급: {level_label(original.current)})"
            if original.current == Level.GUEST:
                tail += "\n화이트리스트에 등록돼 있지 않아요. 관리자에게 등록을 요청하세요."
            await _send_ephemeral(interaction, f"{head}\n{tail}")
            return
        await super().on_error(interaction, error)


# ============================================
# 권한표 점검
# ============================================

def registered_commands(tree: app_commands.CommandTree) -> Dict[str, app_commands.Command]:
    """등록된 슬래시 명령어(말단) qualified name → Command"""
    return {
        cmd.qualified_name: cmd
        for cmd in tree.walk_commands()
        if isinstance(cmd, app_commands.Command)
    }


def usable_commands(tree: app_commands.CommandTree, level: Level) -> List[str]:
    """해당 등급으로 쓸 수 있는 등록된 명령어 이름 (옵션 제한은 고려 안 함)"""
    return sorted(
        name for name in registered_commands(tree)
        if COMMAND_LEVELS.get(name, DEFAULT_LEVEL) <= level
    )


def audit_permission_table(tree: app_commands.CommandTree) -> Dict[str, List]:
    """
    권한표와 실제 등록된 명령어를 비교해서 경고 출력.
    - 표에 없는 명령어 → 소유자 전용으로 막히므로 경고
    - 표에는 있는데 등록 안 된 명령어 → 오타일 수 있어 안내
    - OPTION_LEVELS 에 없는 명령어/옵션 → 경고
    """
    commands = registered_commands(tree)
    registered: Set[str] = set(commands)

    unmapped = sorted(registered - COMMAND_LEVELS.keys())
    missing = sorted(COMMAND_LEVELS.keys() - registered)
    bad_options = sorted(
        (cmd_name, opt_name)
        for (cmd_name, opt_name) in OPTION_LEVELS
        if cmd_name not in commands
        or opt_name not in {p.name for p in commands[cmd_name].parameters}
    )

    if unmapped:
        print(
            f"[권한] ⚠️ 권한표에 없는 명령어 {len(unmapped)}개 → "
            f"{josa(level_label(DEFAULT_LEVEL), '으로', '로')} 막힘: {', '.join(unmapped)}"
        )
    if missing:
        print(f"[권한] ℹ️ 권한표에는 있지만 등록 안 된 명령어: {', '.join(missing)}")
    if bad_options:
        print(f"[권한] ⚠️ OPTION_LEVELS 잘못된 항목: {bad_options}")
    if not (unmapped or missing or bad_options):
        print(f"[권한] 권한표 점검 완료: 명령어 {len(registered)}개 모두 등록됨")

    return {"unmapped": unmapped, "missing": missing, "bad_options": bad_options}
