"""
마인크래프트 서버 관리 슬래시 명령어
경로: modules/minecraft/ServerCommands.py
"""

import discord
from discord import app_commands
from typing import Optional


def setup_commands(bot):
    """마인크래프트 서버 관련 슬래시 명령어 등록"""
    
    # 서버 ID 자동완성 - 데코레이터에서 참조되므로 먼저 정의해야 함
    async def server_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """서버 ID 자동완성"""
        try:
            servers = bot.mc.get_all_server_ids()
            choices = []
            
            for sid in servers:
                config = bot.mc.get_server_config(sid)
                if config is None:  # 설정이 없으면 건너뛰기
                    continue
                
                server_name = config.get('name', sid)
                
                # 검색어 필터링
                if current.lower() in sid.lower() or current.lower() in server_name.lower():
                    choices.append(
                        app_commands.Choice(name=f"{sid} - {server_name}", value=sid)
                    )
            
            return choices[:25]  # Discord 제한: 최대 25개
        except Exception as e:
            print(f"⚠️ 자동완성 오류: {e}")
            return []
    
    @bot.tree.command(name="서버시작", description="마인크래프트 서버를 시작합니다")
    @app_commands.describe(서버="시작할 서버 (기본: 메인 서버)")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def start_server(interaction: discord.Interaction, 서버: Optional[str] = None):
        """서버 시작"""
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message(
                "❌ 이 명령어는 **서버 관리** 권한이 필요합니다.",
                ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        success, message = await bot.mc.start_server(server_id)
        
        if success:
            await interaction.followup.send(f"✅ {message}")
        else:
            await interaction.followup.send(f"❌ {message}")
    
    @bot.tree.command(name="서버중지", description="마인크래프트 서버를 중지합니다")
    @app_commands.describe(
        서버="중지할 서버 (기본: 메인 서버)",
        강제="강제 종료 여부"
    )
    @app_commands.autocomplete(서버=server_autocomplete)
    async def stop_server(interaction: discord.Interaction, 서버: Optional[str] = None, 강제: bool = False):
        """서버 중지"""
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message(
                "❌ 이 명령어는 **서버 관리** 권한이 필요합니다.",
                ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        success, message = await bot.mc.stop_server(server_id, force=강제)
        
        if success:
            await interaction.followup.send(f"✅ {message}")
        else:
            await interaction.followup.send(f"❌ {message}")
    
    @bot.tree.command(name="서버재시작", description="마인크래프트 서버를 재시작합니다")
    @app_commands.describe(서버="재시작할 서버 (기본: 메인 서버)")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def restart_server(interaction: discord.Interaction, 서버: Optional[str] = None):
        """서버 재시작"""
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message(
                "❌ 이 명령어는 **서버 관리** 권한이 필요합니다.",
                ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        success, message = await bot.mc.restart_server(server_id)
        
        if success:
            await interaction.followup.send(f"✅ {message}")
        else:
            await interaction.followup.send(f"❌ {message}")
    
    @bot.tree.command(name="서버상태", description="마인크래프트 서버 상태를 확인합니다")
    @app_commands.describe(서버="확인할 서버 (기본: 메인 서버)")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def server_status(interaction: discord.Interaction, 서버: Optional[str] = None):
        """서버 상태 확인"""
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # 서버 상태 조회
        status = await bot.mc.get_server_status(server_id)
        performance = await bot.mc.get_server_performance(server_id)
        
        # Embed 생성
        embed = discord.Embed(
            title=f"🎮 {config['name']}",
            description=config.get('description', ''),
            color=discord.Color.green() if status and status.get('online') else discord.Color.red()
        )
        
        # 기본 정보
        embed.add_field(
            name="📊 상태",
            value="🟢 온라인" if status and status.get('online') else "🔴 오프라인",
            inline=True
        )
        
        # 프로세스 상태
        is_running = bot.mc.is_server_running(server_id)
        embed.add_field(
            name="⚙️ 프로세스",
            value="✅ 실행 중" if is_running else "❌ 중지됨",
            inline=True
        )
        
        embed.add_field(
            name="🔌 포트",
            value=str(config['port']),
            inline=True
        )
        
        if status and status.get('online'):
            # 플레이어 정보
            players = status.get('players', {})
            player_names = players.get('names', [])
            player_text = f"{players.get('online', 0)} / {players.get('max', 0)}"
            if player_names:
                player_text += f"\n`{', '.join(player_names[:10])}`"
                if len(player_names) > 10:
                    player_text += f"\n외 {len(player_names) - 10}명..."
            
            embed.add_field(
                name="👥 플레이어",
                value=player_text,
                inline=False
            )
            
            # 버전 정보
            embed.add_field(
                name="📦 버전",
                value=status.get('version', '알 수 없음'),
                inline=True
            )
            
            # 지연시간
            embed.add_field(
                name="⏱️ 핑",
                value=f"{status.get('latency', 0):.1f}ms",
                inline=True
            )
        
        # 성능 정보
        if performance:
            perf_text = f"CPU: {performance['cpu_percent']:.1f}%\n"
            perf_text += f"메모리: {performance['memory_mb']:.0f}MB ({performance['memory_percent']:.1f}%)\n"
            perf_text += f"스레드: {performance['threads']}"
            
            embed.add_field(
                name="💻 성능",
                value=perf_text,
                inline=True
            )
            
            # 가동 시간
            uptime_sec = performance['uptime_seconds']
            hours = int(uptime_sec // 3600)
            minutes = int((uptime_sec % 3600) // 60)
            uptime_text = f"{hours}시간 {minutes}분"
            
            embed.add_field(
                name="⏰ 가동 시간",
                value=uptime_text,
                inline=True
            )
        
        embed.set_footer(text=f"서버 ID: {server_id}")
        
        await interaction.followup.send(embed=embed)
    
    @bot.tree.command(name="서버목록", description="관리 중인 모든 서버 목록을 확인합니다")
    async def server_list(interaction: discord.Interaction):
        """서버 목록"""
        server_ids = bot.mc.get_all_server_ids()
        
        if not server_ids:
            await interaction.response.send_message(
                "❌ 등록된 서버가 없습니다.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🎮 마인크래프트 서버 목록",
            color=discord.Color.blue()
        )
        
        for server_id in server_ids:
            config = bot.mc.get_server_config(server_id)
            is_running = bot.mc.is_server_running(server_id)
            
            status_emoji = "🟢" if is_running else "🔴"
            value = f"{status_emoji} {config.get('description', '설명 없음')}\n"
            value += f"포트: `{config['port']}`"
            
            embed.add_field(
                name=f"{config['name']} ({server_id})",
                value=value,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @bot.tree.command(name="명령어실행", description="서버에 마인크래프트 명령어를 실행합니다")
    @app_commands.describe(
        명령어="실행할 명령어 (예: say Hello, list)",
        서버="대상 서버 (기본: 메인 서버)"
    )
    @app_commands.autocomplete(서버=server_autocomplete)
    async def execute_command(interaction: discord.Interaction, 명령어: str, 서버: Optional[str] = None):
        """명령어 실행"""
        # 관리자 권한 필요
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message(
                "❌ 이 명령어는 **관리자** 권한이 필요합니다.",
                ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        success, message = await bot.mc.send_command(server_id, 명령어)
        
        if success:
            await interaction.response.send_message(
                f"✅ {message}\n서버: {config['name']}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {message}",
                ephemeral=True
            )
    
    @bot.tree.command(name="내아이디", description="본인의 디스코드 유저 ID를 확인합니다")
    async def my_id(interaction: discord.Interaction):
        """디스코드 유저 ID 확인용"""
        from config import BOT_OWNER_ID
        is_owner = interaction.user.id == BOT_OWNER_ID
        owner_status = "✨ **봇 소유자**" if is_owner else ""
        
        message = (
            f"🆔 **당신의 디스코드 ID:** `{interaction.user.id}`\n"
            f"{owner_status}\n\n"
            f"💡 이 ID를 `config.py`의 `BOT_OWNER_ID`에 입력하면 "
            f"관리자 권한 없이도 모든 명령어를 사용할 수 있습니다."
        )
        
        await interaction.response.send_message(message, ephemeral=True)
    
    @bot.tree.command(name="스크린정보", description="서버의 Screen 세션 정보를 확인합니다 (Linux)")
    @app_commands.describe(서버="확인할 서버 (기본: 메인 서버)")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def screen_info(interaction: discord.Interaction, 서버: Optional[str] = None):
        """Screen 세션 정보 (Linux 전용)"""
        import platform
        
        if platform.system() != "Linux":
            await interaction.response.send_message(
                "❌ 이 명령어는 Linux 환경에서만 사용 가능합니다.",
                ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        config = bot.mc.get_server_config(server_id)
        
        if not config:
            await interaction.response.send_message(
                f"❌ 서버를 찾을 수 없습니다: {server_id}",
                ephemeral=True
            )
            return
        
        screen_info = bot.mc.get_screen_info(server_id)
        
        if not screen_info:
            await interaction.response.send_message(
                f"📋 {config['name']} 서버는 Screen 세션을 사용하지 않습니다.\n"
                f"💡 `config.py`에서 `terminal_mode`를 `\"screen\"`으로 설정하세요.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🖥️ {config['name']} - Screen 세션 정보",
            color=discord.Color.blue() if screen_info['exists'] else discord.Color.red()
        )
        
        embed.add_field(
            name="📋 세션명",
            value=f"`{screen_info['session_name']}`",
            inline=False
        )
        
        embed.add_field(
            name="🔗 접속 명령어",
            value=f"```bash\n{screen_info['attach_command']}\n```",
            inline=False
        )
        
        embed.add_field(
            name="🚪 나가기",
            value=f"`{screen_info['detach_keys']}`",
            inline=False
        )
        
        embed.add_field(
            name="📊 상태",
            value="🟢 실행 중" if screen_info['exists'] else "🔴 종료됨",
            inline=True
        )
        
        # 사용 가이드
        guide = (
            "**Screen 세션 사용 가이드:**\n"
            "1. SSH로 서버에 접속\n"
            f"2. `{screen_info['attach_command']}` 실행\n"
            "3. 서버 콘솔이 보이며 직접 명령어 입력 가능\n"
            f"4. 나가려면: `{screen_info['detach_keys']}` (Detach)\n\n"
            "**주의:** Screen에서 `exit`나 Ctrl+C를 누르면 서버가 종료됩니다!"
        )
        
        embed.add_field(
            name="📚 가이드",
            value=guide,
            inline=False
        )
        
        embed.set_footer(text="💡 Discord에서는 /명령어실행 또는 RCON 사용을 권장합니다")
        
        await interaction.response.send_message(embed=embed)