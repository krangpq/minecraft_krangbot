"""
마인크래프트 서버 관리 슬래시 명령어
경로: modules/minecraft/ServerCommands.py
"""

import discord
from discord import app_commands
from typing import Optional
import asyncio


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
    
    # ========================================
    # 기본 명령어 (모든 환경)
    # ========================================
    
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
            # ✅ 프로세스 체크만 수행 (포트 대기 시간 무시)
            is_process_running = bot.mc.is_process_running(server_id)
            # 추가: 실제 온라인 상태도 표시
            is_online = bot.mc.is_server_running(server_id)
            
            # 상태 이모지 결정
            if is_online:
                status_emoji = "🟢"  # 완전 온라인
                status_text = "온라인"
            elif is_process_running:
                status_emoji = "🟡"  # 시작 중
                status_text = "시작 중"
            else:
                status_emoji = "🔴"  # 오프라인
                status_text = "오프라인"
            
            value = f"{status_emoji} **{status_text}**\n"
            value += f"{config.get('description', '설명 없음')}\n"
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
    
    @bot.tree.command(name="백업", description="서버 월드 백업")
    @app_commands.describe(서버="백업할 서버")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def backup_world(interaction: discord.Interaction, 서버: Optional[str] = None):
        """월드 백업"""
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message(
                "❌ 권한이 없습니다.", ephemeral=True
            )
            return
        
        server_id = 서버 or bot.mc.default_server
        await interaction.response.defer()
        
        success, message = await bot.mc.backup_world(server_id)
        
        if success:
            await interaction.followup.send(f"✅ {message}")
        else:
            await interaction.followup.send(f"❌ {message}")
    
    # ========================================
    # GCP 전용 명령어 (GCP 환경에서만 등록)
    # ========================================
    
    # GCP 환경 감지
    from config import IS_GCP_ENVIRONMENT, ENABLE_GCP_CONTROL
    
    if IS_GCP_ENVIRONMENT and ENABLE_GCP_CONTROL:
        print("✅ GCP 제어 명령어 등록 중...")
        
        @bot.tree.command(name="제어채널연결", description="[관리자] 컨트롤러 봇과 제어 채널을 연결합니다")
        @app_commands.describe(
            채널="컨트롤러 봇이 생성한 제어 채널",
            컨트롤러봇아이디="컨트롤러 봇의 Discord ID"
        )
        async def connect_control_channel(
            interaction: discord.Interaction,
            채널: discord.TextChannel,
            컨트롤러봇아이디: str
        ):
            """제어 채널 연결"""
            if not bot.is_authorized(interaction.user, "administrator"):
                await interaction.response.send_message(
                    "❌ 이 명령어는 **관리자** 권한이 필요합니다.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            try:
                controller_id = int(컨트롤러봇아이디)
            except ValueError:
                await interaction.followup.send("❌ 올바른 봇 ID를 입력하세요 (숫자만)")
                return
            
            # config 업데이트
            from datetime import datetime
            from config import GCP_INSTANCE_NAME
            
            bot.config.update(
                control_channel_id=채널.id,
                controller_bot_id=controller_id,
                enable_gcp_control=True,
                gcp_instance_name=GCP_INSTANCE_NAME,
                created_at=datetime.now().isoformat()
            )
            
            # GCP 컨트롤러 초기화
            from modules.gcp import GCPController
            bot.gcp_controller = GCPController(bot, 채널.id, controller_id)
            
            # 연결 테스트
            await interaction.followup.send("🔄 연결 테스트 중...")
            
            connection_ok = await bot.gcp_controller.test_connection()
            
            embed = discord.Embed(
                title="✅ 제어 채널 연결 완료" if connection_ok else "⚠️ 제어 채널 연결됨 (응답 없음)",
                description=f"제어 채널: {채널.mention}",
                color=discord.Color.green() if connection_ok else discord.Color.orange()
            )
            
            embed.add_field(
                name="🤖 컨트롤러 봇",
                value=f"ID: `{controller_id}`",
                inline=False
            )
            
            if connection_ok:
                embed.add_field(
                    name="✅ 연결 상태",
                    value="컨트롤러 봇과 정상적으로 통신합니다.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ 연결 상태",
                    value=(
                        "컨트롤러 봇이 응답하지 않습니다.\n"
                        "• 컨트롤러 봇이 실행 중인지 확인하세요\n"
                        "• `/제어기능토글`로 기능을 활성화했는지 확인하세요"
                    ),
                    inline=False
                )
            
            embed.add_field(
                name="📋 사용 가능한 명령어",
                value=(
                    "• `/자동종료` - 마크 서버 + GCP 자동 종료\n"
                    "• `/gcp상태확인` - GCP 인스턴스 상태 확인\n"
                    "• `/제어기능상태` - 현재 설정 확인"
                ),
                inline=False
            )
            
            embed.set_footer(text=f"설정 파일: {bot.config.config_file}")
            
            await interaction.followup.send(embed=embed)
            
            # 제어 채널에 연결 알림
            await 채널.send(
                f"🤝 **마인크래프트 봇 연결됨**\n"
                f"봇: {bot.user.name}\n"
                f"봇 ID: `{bot.user.id}`\n"
                f"GCP 인스턴스: `{bot.config.get('gcp_instance_name')}`\n"
                f"상태: 🟢 연결됨"
            )
            
            print(f"✅ 제어 채널 연결: #{채널.name} (ID: {채널.id})")
            print(f"✅ 컨트롤러 봇 ID: {controller_id}")
        
        @bot.tree.command(name="제어채널해제", description="[관리자] 제어 채널 연결을 해제합니다")
        async def disconnect_control_channel(interaction: discord.Interaction):
            """제어 채널 연결 해제"""
            if not bot.is_authorized(interaction.user, "administrator"):
                await interaction.response.send_message(
                    "❌ 이 명령어는 **관리자** 권한이 필요합니다.",
                    ephemeral=True
                )
                return
            
            if not bot.config:
                await interaction.response.send_message(
                    "ℹ️ 설정이 초기화되지 않았습니다.",
                    ephemeral=True
                )
                return
            
            control_channel_id = bot.config.get('control_channel_id')
            
            if not control_channel_id:
                await interaction.response.send_message(
                    "ℹ️ 연결된 제어 채널이 없습니다.",
                    ephemeral=True
                )
                return
            
            # 제어 채널에 해제 알림
            try:
                channel = bot.get_channel(control_channel_id)
                if channel:
                    await channel.send(
                        f"👋 **마인크래프트 봇 연결 해제**\n"
                        f"봇: {bot.user.name}\n"
                        f"상태: 🔴 연결 해제됨"
                    )
            except:
                pass
            
            # 설정 초기화
            bot.config.reset()
            bot.gcp_controller = None
            
            await interaction.response.send_message(
                "✅ 제어 채널 연결이 해제되었습니다.",
                ephemeral=True
            )
            
            print(f"🔄 제어 채널 연결 해제")
        
        @bot.tree.command(name="제어기능상태", description="GCP 제어 기능 상태를 확인합니다")
        async def control_status(interaction: discord.Interaction):
            """제어 기능 상태 확인"""
            if not bot.config:
                await interaction.response.send_message(
                    "⚠️ 설정이 초기화되지 않았습니다.\n"
                    "관리자가 `/제어채널연결`을 실행하세요.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="📊 GCP 제어 기능 상태",
                color=discord.Color.blue() if bot.config.get('enable_gcp_control') else discord.Color.red()
            )
            
            # 설정 요약
            embed.add_field(
                name="⚙️ 설정",
                value=bot.config.export_summary(),
                inline=False
            )
            
            # 제어 채널 상태
            control_channel_id = bot.config.get('control_channel_id')
            if control_channel_id:
                channel = bot.get_channel(control_channel_id)
                if channel:
                    embed.add_field(
                        name="📡 제어 채널",
                        value=f"✅ {channel.mention}",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="📡 제어 채널",
                        value=f"❌ 채널을 찾을 수 없음\n(ID: {control_channel_id})",
                        inline=True
                    )
            else:
                embed.add_field(
                    name="📡 제어 채널",
                    value="❌ 미설정",
                    inline=True
                )
            
            # 컨트롤러 봇 상태
            controller_id = bot.config.get('controller_bot_id')
            if controller_id:
                try:
                    controller = await bot.fetch_user(controller_id)
                    embed.add_field(
                        name="🤖 컨트롤러 봇",
                        value=f"✅ {controller.name}\n(ID: `{controller_id}`)",
                        inline=True
                    )
                except:
                    embed.add_field(
                        name="🤖 컨트롤러 봇",
                        value=f"⚠️ ID: `{controller_id}`\n(봇을 찾을 수 없음)",
                        inline=True
                    )
            else:
                embed.add_field(
                    name="🤖 컨트롤러 봇",
                    value="❌ 미연결",
                    inline=True
                )
            
            # GCP 인스턴스 정보
            embed.add_field(
                name="☁️ GCP 인스턴스",
                value=f"`{bot.config.get('gcp_instance_name')}`",
                inline=False
            )
            
            # 연결 테스트 버튼
            if bot.config.get('enable_gcp_control') and bot.gcp_controller:
                embed.add_field(
                    name="🧪 연결 테스트",
                    value="제어 채널에 `!ping`을 입력하여 연결을 테스트하세요.",
                    inline=False
                )
            
            if not bot.config.get('enable_gcp_control'):
                embed.add_field(
                    name="💡 활성화 방법",
                    value="관리자가 `/제어채널연결` 명령어를 사용하세요",
                    inline=False
                )
            
            embed.set_footer(text=f"설정 파일: {bot.config.config_file}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @bot.tree.command(name="자동종료", description="모든 마크 서버를 정리하고 GCP 인스턴스까지 자동 종료")
        async def auto_shutdown(interaction: discord.Interaction):
            """완전 자동화된 종료 프로세스"""
            if not bot.is_authorized(interaction.user, "manage_guild"):
                await interaction.response.send_message(
                    "❌ 이 명령어는 **서버 관리** 권한이 필요합니다.",
                    ephemeral=True
                )
                return
            
            # GCP 제어 기능 확인
            if not bot.config or not bot.config.get('enable_gcp_control') or not bot.gcp_controller:
                await interaction.response.send_message(
                    "❌ GCP 제어 기능이 비활성화되어 있습니다.\n"
                    "관리자에게 `/제어채널연결`을 요청하세요.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer()
            
            embed = discord.Embed(
                title="🔄 자동 종료 프로세스 시작",
                color=discord.Color.orange()
            )
            
            # 1단계: 실행 중인 서버 확인
            running_servers = []
            for server_id in bot.mc.get_all_server_ids():
                if bot.mc.is_server_running(server_id):
                    running_servers.append(server_id)
            
            if not running_servers:
                embed.add_field(
                    name="1️⃣ 마인크래프트 서버",
                    value="✅ 실행 중인 서버 없음",
                    inline=False
                )
            else:
                embed.add_field(
                    name="1️⃣ 마인크래프트 서버 중지 중...",
                    value=f"대상: {', '.join(running_servers)}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
            # 2단계: 각 서버 중지
            for server_id in running_servers:
                config = bot.mc.get_server_config(server_id)
                success, message = await bot.mc.stop_server(server_id)
                
                status = "✅" if success else "❌"
                await interaction.followup.send(f"{status} {config['name']}: {message}")
                
                await asyncio.sleep(2)
            
            # 모든 서버 중지 대기
            if running_servers:
                await interaction.followup.send("⏳ 서버 종료 완료 대기 중... (10초)")
                await asyncio.sleep(10)
            
            # 3단계: GCP 인스턴스 중지 요청
            await interaction.followup.send("☁️ **GCP 인스턴스 중지 요청 중...**")
            
            from config import GCP_INSTANCE_NAME
            instance_name = bot.config.get('gcp_instance_name', GCP_INSTANCE_NAME)
            
            success, response = await bot.gcp_controller.send_shutdown_request(
                instance=instance_name,
                reason="자동 종료 프로세스"
            )
            
            if success:
                final_embed = discord.Embed(
                    title="✅ 자동 종료 완료",
                    description=(
                        "모든 마인크래프트 서버가 정상 종료되었으며,\n"
                        "GCP 인스턴스도 중지되었습니다.\n\n"
                        "💰 비용 절감 모드 활성화!"
                    ),
                    color=discord.Color.green()
                )
                
                final_embed.add_field(
                    name="📋 요약",
                    value=(
                        f"• 마크 서버: {len(running_servers)}개 중지\n"
                        f"• GCP 인스턴스: `{instance_name}` 중지\n"
                    ),
                    inline=False
                )
                
                await interaction.followup.send(embed=final_embed)
            else:
                await interaction.followup.send(
                    f"⚠️ GCP 인스턴스 중지 실패\n{response}\n\n"
                    f"수동으로 VPN 서버 봇에서 `/인스턴스중지` 명령어를 사용하세요."
                )
        
        @bot.tree.command(name="gcp상태확인", description="GCP 인스턴스 상태를 확인합니다")
        async def check_gcp_status(interaction: discord.Interaction):
            """GCP 인스턴스 상태 확인"""
            
            # GCP 제어 기능 확인
            if not bot.config or not bot.config.get('enable_gcp_control') or not bot.gcp_controller:
                await interaction.response.send_message(
                    "❌ GCP 제어 기능이 비활성화되어 있습니다.\n"
                    "관리자에게 `/제어채널연결`을 요청하세요.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer()
            
            from config import GCP_INSTANCE_NAME
            instance_name = bot.config.get('gcp_instance_name', GCP_INSTANCE_NAME)
            
            success, response = await bot.gcp_controller.check_status(instance_name)
            
            embed = discord.Embed(
                title=f"☁️ GCP 인스턴스 상태: {instance_name}",
                description=response if success else "⚠️ 상태 확인 실패",
                color=discord.Color.blue() if success else discord.Color.red()
            )
            
            if not success:
                embed.add_field(
                    name="💡 해결 방법",
                    value=(
                        "• 컨트롤러 봇이 실행 중인지 확인\n"
                        "• VPN 서버에서 `/제어기능토글` 확인\n"
                        "• `/제어기능상태`로 연결 상태 확인"
                    ),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
        
        print("✅ GCP 제어 명령어 등록 완료")
    else:
        print("ℹ️ 로컬 환경 - GCP 제어 명령어 미등록")