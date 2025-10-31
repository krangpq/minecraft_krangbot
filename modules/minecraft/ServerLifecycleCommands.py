"""
서버 생성/삭제/업그레이드 슬래시 명령어
경로: modules/minecraft/ServerLifecycleCommands.py
"""

import discord
from discord import app_commands
from typing import Optional
import tempfile
import time
from pathlib import Path
import asyncio

def setup_lifecycle_commands(bot):
    """서버 생명주기 관리 명령어 등록"""
    
    async def core_type_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        cores = ['paper', 'spigot', 'vanilla', 'fabric', 'forge']
        return [app_commands.Choice(name=c, value=c) for c in cores if current.lower() in c.lower()][:25]
    
    async def version_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            available_cores = bot.core_manager.get_available_cores()
            versions = []
            
            for core_type, core_versions in available_cores.items():
                for version in core_versions:
                    if current.lower() in version.lower():
                        versions.append(app_commands.Choice(name=f"{core_type} {version}", value=version))
            
            return versions[:25]
        except:
            return []
    
    async def plugin_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            plugins = bot.core_manager.get_available_plugins()
            return [app_commands.Choice(name=p, value=p) for p in plugins if current.lower() in p.lower()][:25]
        except:
            return []
    
    async def server_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            servers = bot.mc.get_all_server_ids()
            choices = []
            
            for sid in servers:
                config = bot.mc.get_server_config(sid)
                if config is None:
                    continue
                
                server_name = config.get('name', sid)
                
                if current.lower() in sid.lower() or current.lower() in server_name.lower():
                    choices.append(app_commands.Choice(name=f"{sid} - {server_name}", value=sid))
            
            return choices[:25]
        except:
            return []
    
    @bot.tree.command(name="서버생성", description="새 마인크래프트 서버 생성")
    @app_commands.describe(
        서버이름="서버 ID (영문, 숫자, 언더스코어만)",
        구동기="서버 구동기 종류",
        버전="마인크래프트 버전",
        최소메모리="최소 메모리 (MB, 선택)",
        최대메모리="최대 메모리 (MB, 선택)",
        설명="서버 설명 (선택)"
    )
    @app_commands.autocomplete(구동기=core_type_autocomplete, 버전=version_autocomplete)
    async def create_server(
        interaction: discord.Interaction,
        서버이름: str,
        구동기: str,
        버전: str,
        최소메모리: Optional[int] = None,
        최대메모리: Optional[int] = None,
        설명: Optional[str] = None
    ):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        success, message, config = await bot.lifecycle_manager.create_server(
            server_id=서버이름,
            core_type=구동기,
            version=버전,
            min_memory=최소메모리,
            max_memory=최대메모리,
            description=설명 or ""
        )
        
        if success:
            embed = discord.Embed(title="서버 생성 완료", color=discord.Color.green())
            embed.add_field(name="서버 ID", value=서버이름, inline=False)
            embed.add_field(name="구동기", value=f"{구동기} {버전}", inline=True)
            
            if config:
                mem = config['memory']
                embed.add_field(name="메모리", value=f"{mem['min']}-{mem['max']}MB", inline=True)
            
            embed.add_field(name="다음", value="봇 재시작 필요", inline=False)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"생성 실패: {message}")
    
    @bot.tree.command(name="서버삭제", description="서버 삭제")
    @app_commands.describe(서버="삭제할 서버", 강제삭제="백업 없이 삭제")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def delete_server(interaction: discord.Interaction, 서버: str, 강제삭제: bool = False):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        success, message = await bot.lifecycle_manager.delete_server(서버, force=강제삭제)
        
        if success:
            await interaction.followup.send(f"삭제 완료: {서버}\n백업 보관: 30일")
        else:
            await interaction.followup.send(f"삭제 실패: {message}")
    
    @bot.tree.command(name="서버업그레이드", description="서버 버전 업그레이드")
    @app_commands.describe(서버="대상 서버", 새버전="새 버전", 새구동기="새 구동기 (선택)")
    @app_commands.autocomplete(서버=server_autocomplete, 새버전=version_autocomplete, 새구동기=core_type_autocomplete)
    async def upgrade_server(interaction: discord.Interaction, 서버: str, 새버전: str, 새구동기: Optional[str] = None):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        success, message = await bot.lifecycle_manager.upgrade_server(서버, 새버전, 새구동기)
        
        if success:
            embed = discord.Embed(title="업그레이드 완료", color=discord.Color.green())
            embed.add_field(name="서버", value=서버, inline=False)
            embed.add_field(name="결과", value=message, inline=False)
            embed.add_field(name="백업", value="30일 보관", inline=True)
            embed.add_field(name="주의", value="재시작 필요", inline=True)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"업그레이드 실패: {message}")
    
    @bot.tree.command(name="서버롤백", description="서버를 이전 버전으로 롤백")
    @app_commands.describe(서버="롤백할 서버")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def rollback_server(interaction: discord.Interaction, 서버: str):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        success, message = await bot.lifecycle_manager.rollback_server(서버)
        
        if success:
            await interaction.followup.send(f"롤백 완료: {message}\n재시작 필요")
        else:
            await interaction.followup.send(f"롤백 실패: {message}")
    
    @bot.tree.command(name="플러그인추가", description="서버에 플러그인 추가")
    @app_commands.describe(서버="대상 서버", 플러그인="추가할 플러그인")
    @app_commands.autocomplete(서버=server_autocomplete, 플러그인=plugin_autocomplete)
    async def add_plugin(interaction: discord.Interaction, 서버: str, 플러그인: str):
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        success, message = bot.lifecycle_manager.add_plugin_to_server(서버, 플러그인)
        
        if success:
            await interaction.response.send_message(f"{message}\n재시작 필요")
        else:
            await interaction.response.send_message(f"실패: {message}", ephemeral=True)
    
    @bot.tree.command(name="구동기목록", description="사용 가능한 구동기 확인")
    async def list_cores(interaction: discord.Interaction):
        cores = bot.core_manager.get_available_cores()
        
        if not cores:
            await interaction.response.send_message("구동기 없음", ephemeral=True)
            return
        
        embed = discord.Embed(title="구동기 목록", color=discord.Color.blue())
        
        for core_type, versions in cores.items():
            features = []
            if bot.core_manager.supports_plugins(core_type):
                features.append("플러그인")
            if bot.core_manager.is_modded(core_type):
                features.append("모드")
            
            feature_text = f"({', '.join(features)})" if features else ""
            
            versions_text = ', '.join(versions[:10])
            if len(versions) > 10:
                versions_text += f" 외 {len(versions) - 10}개"
            
            embed.add_field(name=f"{core_type.upper()} {feature_text}", value=versions_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @bot.tree.command(name="플러그인목록", description="사용 가능한 플러그인 확인")
    async def list_plugins(interaction: discord.Interaction):
        plugins = bot.core_manager.get_available_plugins()
        
        if not plugins:
            await interaction.response.send_message("플러그인 없음", ephemeral=True)
            return
        
        embed = discord.Embed(title="플러그인 목록", color=discord.Color.blue())
        embed.description = '\n'.join([f"• {p}" for p in plugins])
        
        await interaction.response.send_message(embed=embed)
    
    @bot.tree.command(name="구동기업데이트", description="구동기 및 플러그인 업데이트")
    async def update_cores(interaction: discord.Interaction):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        await interaction.followup.send("업데이트 시작 (시간 소요)")
        
        await bot.core_manager.update_all_cores()
        
        await interaction.followup.send("업데이트 완료")
    
    @bot.tree.command(name="백업정리", description="오래된 백업 삭제")
    async def cleanup_backups(interaction: discord.Interaction):
        if not bot.is_authorized(interaction.user, "administrator"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        success, message = await bot.lifecycle_manager.cleanup_old_backups()
        
        await interaction.followup.send(message)
    
    @bot.tree.command(name="모드추가", description="모드 jar 파일을 서버에 추가")
    @app_commands.describe(서버="대상 서버")
    @app_commands.autocomplete(서버=server_autocomplete)
    async def add_mod_command(interaction: discord.Interaction, 서버: str):
        if not bot.is_authorized(interaction.user, "manage_guild"):
            await interaction.response.send_message("권한 없음", ephemeral=True)
            return
        
        await interaction.response.send_message(
            f"{서버} 서버에 추가할 모드 jar 파일을 이 채널에 업로드하세요.\n"
            f"60초 이내에 업로드해주세요.",
            ephemeral=True
        )
        
        def check(m):
            return (
                m.author.id == interaction.user.id and
                m.channel.id == interaction.channel_id and
                len(m.attachments) > 0 and
                m.attachments[0].filename.endswith('.jar')
            )
        
        temp_file = None
        
        try:
            message = await bot.wait_for('message', check=check, timeout=60.0)
            
            attachment = message.attachments[0]
            
            # 파일 크기 제한 (100MB)
            if attachment.size > 100 * 1024 * 1024:
                await message.reply("파일 크기가 100MB를 초과합니다")
                return
            
            # 임시 파일 저장 (고유 파일명)
            temp_dir = Path(tempfile.gettempdir())
            timestamp = int(time.time() * 1000)
            temp_file = temp_dir / f"{timestamp}_{attachment.filename}"
            
            await attachment.save(temp_file)
            
            # 모드 추가
            success, result_message = bot.lifecycle_manager.add_mod_to_server(서버, temp_file)
            
            if success:
                await message.reply(f"{result_message}\n서버 재시작 필요")
            else:
                await message.reply(f"모드 추가 실패: {result_message}")
        
        except asyncio.TimeoutError:
            await interaction.followup.send("시간 초과 - 60초 이내 업로드 필요", ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"오류 발생: {e}", ephemeral=True)
        
        finally:
            # 임시 파일 삭제
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
    
    @bot.tree.command(name="spigot빌드상태", description="Spigot 빌드 진행 상황 확인")
    async def spigot_build_status(interaction: discord.Interaction):
        status = bot.core_manager.get_spigot_build_status()
        
        if not status:
            await interaction.response.send_message("빌드 중인 Spigot 없음", ephemeral=True)
            return
        
        embed = discord.Embed(title="Spigot 빌드 상태", color=discord.Color.blue())
        
        for version, state in status.items():
            status_text = "빌드 중" if state == 'building' else "완료"
            embed.add_field(name=f"Spigot {version}", value=status_text, inline=True)
        
        embed.set_footer(text="빌드는 백그라운드에서 진행됩니다")
        
        await interaction.response.send_message(embed=embed)