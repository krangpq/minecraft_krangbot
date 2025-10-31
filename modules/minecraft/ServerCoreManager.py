"""
마인크래프트 서버 구동기 관리 (Paper, Spigot, Vanilla, Fabric, Forge)
경로: modules/minecraft/ServerCoreManager.py
"""

import aiohttp
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import json
import shutil
from datetime import datetime


class ServerCoreManager:
    """서버 구동기 자동 다운로드 및 관리"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.cores_dir = base_path / 'server_cores'
        self.plugins_dir = base_path / 'plugins'
        
        self.cores_dir.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        self.core_types = {
            'paper': {'modded': False, 'plugins': True},
            'spigot': {'modded': False, 'plugins': True},
            'vanilla': {'modded': False, 'plugins': False},
            'fabric': {'modded': True, 'plugins': False},
            'forge': {'modded': True, 'plugins': False}
        }
        
        self.auto_plugins = ['worldedit', 'essentialsx', 'geyser']
        
        # Spigot 빌드 상태
        self.building_spigot = {}  # {version: asyncio.Task}
        self.spigot_build_lock = asyncio.Lock()
    
    async def update_all_cores(self):
        """모든 구동기 업데이트"""
        print("\n구동기 업데이트 시작")
        
        tasks = [
            self.update_paper(),
            self.update_vanilla(),
            self.update_fabric(),
            self.update_forge(),
            self.update_plugins()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Spigot 백그라운드 빌드
        await self.start_spigot_background_builds()
    
    async def start_spigot_background_builds(self):
        """Spigot 주요 버전 백그라운드 빌드"""
        major_versions = ['1.21.1', '1.20.6', '1.20.4', '1.20.1', '1.19.4']
        
        print("\nSpigot 백그라운드 빌드 시작")
        
        for version in major_versions:
            version_dir = self.cores_dir / 'spigot' / version
            jar_file = version_dir / 'server.jar'
            
            if jar_file.exists():
                continue
            
            task = asyncio.create_task(self._build_spigot_background(version))
            self.building_spigot[version] = task
            
            print(f"  Spigot {version} 빌드 대기열 추가")
    
    async def _build_spigot_background(self, version: str):
        """Spigot Screen 세션 빌드"""
        try:
            print(f"\n[Spigot {version}] 빌드 시작")
            
            version_dir = self.cores_dir / 'spigot' / version
            version_dir.mkdir(parents=True, exist_ok=True)
            
            buildtools_path = version_dir / 'BuildTools.jar'
            
            # BuildTools 다운로드
            async with aiohttp.ClientSession() as session:
                url = 'https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar'
                async with session.get(url) as resp:
                    with open(buildtools_path, 'wb') as f:
                        f.write(await resp.read())
            
            print(f"[Spigot {version}] BuildTools 다운로드 완료")
            
            # 빌드 상태 파일
            build_state_file = version_dir / '.building'
            with open(build_state_file, 'w') as f:
                json.dump({
                    'version': version,
                    'started_at': datetime.now().isoformat(),
                    'status': 'building'
                }, f)
            
            # Screen 세션으로 BuildTools 실행
            import platform
            if platform.system() == "Linux":
                try:
                    from modules.minecraft.ScreenManager import ScreenManager
                    
                    session_name = f"spigot_build_{version.replace('.', '_')}"
                    build_command = f"java -jar {buildtools_path} --rev {version}"
                    
                    # 기존 세션 확인 및 종료
                    if ScreenManager.screen_exists(session_name):
                        print(f"[Spigot {version}] 기존 빌드 세션 종료 중...")
                        await ScreenManager().kill_screen(session_name)
                        await asyncio.sleep(2)
                    
                    # Screen 세션 생성
                    print(f"[Spigot {version}] Screen 세션 생성: {session_name}")
                    success, message, actual_session = await ScreenManager().create_screen(
                        session_name=session_name,
                        command=build_command,
                        cwd=str(version_dir),
                        reuse_existing=True
                    )
                    
                    if success and actual_session:
                        print(f"[Spigot {version}] 빌드 진행 중 - Screen 세션: {actual_session}")
                        print(f"💡 빌드 과정을 보려면: screen -r {actual_session}")
                        
                        # 세션이 종료될 때까지 대기
                        while ScreenManager.screen_exists(session_name):
                            await asyncio.sleep(10)
                        
                        print(f"[Spigot {version}] Screen 세션 종료 - 빌드 결과 확인 중...")
                    else:
                        print(f"[Spigot {version}] Screen 생성 실패, 백그라운드로 빌드")
                        raise ImportError  # 폴백
                    
                except ImportError:
                    # Screen 사용 불가 시 백그라운드 빌드
                    print(f"[Spigot {version}] 백그라운드 빌드")
                    process = await asyncio.create_subprocess_exec(
                        'java', '-jar', str(buildtools_path), '--rev', version,
                        cwd=str(version_dir),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.wait()
            else:
                # Windows/macOS - 백그라운드 빌드
                print(f"[Spigot {version}] 백그라운드 빌드 (비 Linux 환경)")
                process = await asyncio.create_subprocess_exec(
                    'java', '-jar', str(buildtools_path), '--rev', version,
                    cwd=str(version_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.wait()
            
            # 빌드 결과 확인
            spigot_jar = list(version_dir.glob(f'spigot-{version}.jar'))
            if spigot_jar:
                shutil.move(str(spigot_jar[0]), str(version_dir / 'server.jar'))
                print(f"[Spigot {version}] ✅ 빌드 완료")
                
                with open(build_state_file, 'w') as f:
                    json.dump({
                        'version': version,
                        'completed_at': datetime.now().isoformat(),
                        'status': 'success'
                    }, f)
            else:
                print(f"[Spigot {version}] ❌ 빌드 실패: jar 파일 없음")
                with open(build_state_file, 'w') as f:
                    json.dump({
                        'version': version,
                        'completed_at': datetime.now().isoformat(),
                        'status': 'failed',
                        'error': 'jar not found'
                    }, f)
            
        except Exception as e:
            print(f"[Spigot {version}] ❌ 빌드 오류: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if version in self.building_spigot:
                del self.building_spigot[version]
    
    def is_spigot_building(self, version: str) -> bool:
        """Spigot 빌드 중인지 확인"""
        return version in self.building_spigot
    
    def get_spigot_build_status(self) -> Dict[str, str]:
        """빌드 중인 Spigot 버전"""
        status = {}
        for version, task in self.building_spigot.items():
            status[version] = 'completed' if task.done() else 'building'
        return status
    
    async def wait_for_builds_completion(self):
        """모든 Spigot 빌드 완료 대기"""
        if not self.building_spigot:
            return
        
        print("\nSpigot 빌드 완료 대기")
        tasks = list(self.building_spigot.values())
        await asyncio.gather(*tasks, return_exceptions=True)
        print("모든 Spigot 빌드 완료")
    
    async def update_paper(self):
        """Paper 다운로드"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://papermc.io/api/v2/projects/paper') as resp:
                    data = await resp.json()
                    versions = data['versions']
                
                for version in versions[-5:]:
                    version_dir = self.cores_dir / 'paper' / version
                    version_dir.mkdir(parents=True, exist_ok=True)
                    
                    jar_file = version_dir / 'server.jar'
                    if jar_file.exists():
                        continue
                    
                    async with session.get(f'https://papermc.io/api/v2/projects/paper/versions/{version}') as resp:
                        version_data = await resp.json()
                        build = version_data['builds'][-1]
                    
                    download_url = f'https://papermc.io/api/v2/projects/paper/versions/{version}/builds/{build}/downloads/paper-{version}-{build}.jar'
                    
                    async with session.get(download_url) as resp:
                        with open(jar_file, 'wb') as f:
                            f.write(await resp.read())
                    
                    print(f"Paper {version} 다운로드")
        
        except Exception as e:
            print(f"Paper 실패: {e}")
    
    async def update_vanilla(self):
        """Vanilla 다운로드"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://launchermeta.mojang.com/mc/game/version_manifest.json') as resp:
                    manifest = await resp.json()
                
                for version_info in manifest['versions'][:10]:
                    if version_info['type'] != 'release':
                        continue
                    
                    version = version_info['id']
                    version_dir = self.cores_dir / 'vanilla' / version
                    version_dir.mkdir(parents=True, exist_ok=True)
                    
                    jar_file = version_dir / 'server.jar'
                    if jar_file.exists():
                        continue
                    
                    async with session.get(version_info['url']) as resp:
                        version_data = await resp.json()
                        download_url = version_data['downloads']['server']['url']
                    
                    async with session.get(download_url) as resp:
                        with open(jar_file, 'wb') as f:
                            f.write(await resp.read())
                    
                    print(f"Vanilla {version} 다운로드")
        
        except Exception as e:
            print(f"Vanilla 실패: {e}")
    
    async def update_fabric(self):
        """Fabric 다운로드"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://meta.fabricmc.net/v2/versions/game') as resp:
                    versions = await resp.json()
                
                async with session.get('https://meta.fabricmc.net/v2/versions/loader') as resp:
                    loaders = await resp.json()
                    loader_version = loaders[0]['version']
                
                async with session.get('https://meta.fabricmc.net/v2/versions/installer') as resp:
                    installers = await resp.json()
                    installer_version = installers[0]['version']
                
                for version_info in versions[:10]:
                    if not version_info['stable']:
                        continue
                    
                    version = version_info['version']
                    version_dir = self.cores_dir / 'fabric' / version
                    version_dir.mkdir(parents=True, exist_ok=True)
                    
                    jar_file = version_dir / 'server.jar'
                    if jar_file.exists():
                        continue
                    
                    download_url = f'https://meta.fabricmc.net/v2/versions/loader/{version}/{loader_version}/{installer_version}/server/jar'
                    
                    async with session.get(download_url) as resp:
                        with open(jar_file, 'wb') as f:
                            f.write(await resp.read())
                    
                    print(f"Fabric {version} 다운로드")
        
        except Exception as e:
            print(f"Fabric 실패: {e}")
    
    async def update_forge(self):
        """Forge 다운로드"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json') as resp:
                    data = await resp.json()
                    promos = data['promos']
                
                for key, build in list(promos.items())[:20]:
                    if not key.endswith('-latest'):
                        continue
                    
                    version = key.replace('-latest', '')
                    version_dir = self.cores_dir / 'forge' / version
                    version_dir.mkdir(parents=True, exist_ok=True)
                    
                    jar_file = version_dir / 'server.jar'
                    if jar_file.exists():
                        continue
                    
                    download_url = f'https://maven.minecraftforge.net/net/minecraftforge/forge/{version}-{build}/forge-{version}-{build}-installer.jar'
                    
                    async with session.get(download_url) as resp:
                        if resp.status == 200:
                            with open(jar_file, 'wb') as f:
                                f.write(await resp.read())
                            print(f"Forge {version} 다운로드")
        
        except Exception as e:
            print(f"Forge 실패: {e}")
    
    async def update_plugins(self):
        """플러그인 업데이트"""
        tasks = [
            self._update_worldedit(),
            self._update_essentialsx(),
            self._update_geyser()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _update_worldedit(self):
        """WorldEdit 다운로드"""
        try:
            plugin_dir = self.plugins_dir / 'worldedit'
            plugin_dir.mkdir(exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.github.com/repos/EngineHub/WorldEdit/releases/latest') as resp:
                    data = await resp.json()
                    
                    for asset in data['assets']:
                        if 'bukkit' in asset['name'].lower() and asset['name'].endswith('.jar'):
                            download_url = asset['browser_download_url']
                            
                            async with session.get(download_url) as dl_resp:
                                jar_file = plugin_dir / asset['name']
                                with open(jar_file, 'wb') as f:
                                    f.write(await dl_resp.read())
                            
                            print(f"WorldEdit 다운로드")
                            break
        except Exception as e:
            print(f"WorldEdit 실패: {e}")
    
    async def _update_essentialsx(self):
        """EssentialsX 다운로드"""
        try:
            plugin_dir = self.plugins_dir / 'essentialsx'
            plugin_dir.mkdir(exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.github.com/repos/EssentialsX/Essentials/releases/latest') as resp:
                    data = await resp.json()
                    
                    for asset in data['assets']:
                        if 'EssentialsX-' in asset['name'] and asset['name'].endswith('.jar'):
                            download_url = asset['browser_download_url']
                            
                            async with session.get(download_url) as dl_resp:
                                jar_file = plugin_dir / asset['name']
                                with open(jar_file, 'wb') as f:
                                    f.write(await dl_resp.read())
                            
                            print(f"EssentialsX 다운로드")
                            break
        except Exception as e:
            print(f"EssentialsX 실패: {e}")
    
    async def _update_geyser(self):
        """Geyser 다운로드"""
        try:
            plugin_dir = self.plugins_dir / 'geyser'
            plugin_dir.mkdir(exist_ok=True)
            
            download_url = 'https://download.geysermc.org/v2/projects/geyser/versions/latest/builds/latest/downloads/spigot'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as resp:
                    jar_file = plugin_dir / 'Geyser-Spigot.jar'
                    with open(jar_file, 'wb') as f:
                        f.write(await resp.read())
            
            print(f"Geyser 다운로드")
        except Exception as e:
            print(f"Geyser 실패: {e}")
    
    def get_available_cores(self) -> Dict[str, List[str]]:
        """사용 가능한 구동기 목록"""
        cores = {}
        
        for core_type in self.core_types.keys():
            core_dir = self.cores_dir / core_type
            if core_dir.exists():
                versions = [v.name for v in core_dir.iterdir() if v.is_dir() and (v / 'server.jar').exists()]
                cores[core_type] = sorted(versions, reverse=True)
        
        return cores
    
    def get_core_path(self, core_type: str, version: str) -> Optional[Path]:
        """구동기 JAR 경로"""
        jar_file = self.cores_dir / core_type / version / 'server.jar'
        return jar_file if jar_file.exists() else None
    
    def supports_plugins(self, core_type: str) -> bool:
        """플러그인 지원 여부"""
        return self.core_types.get(core_type, {}).get('plugins', False)
    
    def is_modded(self, core_type: str) -> bool:
        """모드 서버 여부"""
        return self.core_types.get(core_type, {}).get('modded', False)
    
    def get_available_plugins(self) -> List[str]:
        """사용 가능한 플러그인"""
        plugins = []
        
        if self.plugins_dir.exists():
            for plugin_dir in self.plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    jar_files = list(plugin_dir.glob('*.jar'))
                    if jar_files:
                        plugins.append(plugin_dir.name)
        
        return plugins
    
    def get_plugin_jar(self, plugin_name: str) -> Optional[Path]:
        """플러그인 JAR 경로"""
        plugin_dir = self.plugins_dir / plugin_name
        if plugin_dir.exists():
            jar_files = list(plugin_dir.glob('*.jar'))
            return jar_files[0] if jar_files else None
        return None