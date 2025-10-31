"""
서버 생성, 삭제, 버전 업그레이드 관리
경로: modules/minecraft/ServerLifecycleManager.py
"""

import shutil
from pathlib import Path
from typing import Tuple, Optional, Dict
from datetime import datetime, timedelta
import json


class ServerLifecycleManager:
    """서버 생성/삭제/업그레이드 관리"""
    
    def __init__(self, servers_dir: Path, core_manager):
        self.servers_dir = servers_dir
        self.core_manager = core_manager
        self.backups_dir = servers_dir.parent / 'backups'
        self.backups_dir.mkdir(exist_ok=True)
    
    async def create_server(
        self,
        server_id: str,
        core_type: str,
        version: str,
        min_memory: Optional[int] = None,
        max_memory: Optional[int] = None,
        description: str = "",
        plugins: Optional[list] = None
    ) -> Tuple[bool, str, Optional[dict]]:
        """새 서버 생성"""
        try:
            # 서버 폴더 생성
            server_path = self.servers_dir / server_id
            if server_path.exists():
                return False, f"서버가 이미 존재합니다: {server_id}", None
            
            # 구동기 확인
            core_jar = self.core_manager.get_core_path(core_type, version)
            if not core_jar:
                return False, f"{core_type} {version}을 찾을 수 없습니다", None
            
            # 폴더 생성
            server_path.mkdir(parents=True)
            
            # 구동기 복사
            shutil.copy(core_jar, server_path / 'server.jar')
            
            # 플러그인 설치
            if plugins and self.core_manager.supports_plugins(core_type):
                plugins_dir = server_path / 'plugins'
                plugins_dir.mkdir()
                
                for plugin_name in plugins:
                    plugin_jar = self.core_manager.get_plugin_jar(plugin_name)
                    if plugin_jar:
                        shutil.copy(plugin_jar, plugins_dir / plugin_jar.name)
            
            # 모드 서버인 경우 mods 폴더 생성
            if self.core_manager.is_modded(core_type):
                (server_path / 'mods').mkdir()
            
            # bot_config.json 생성
            from config import DEFAULT_MIN_MEMORY, DEFAULT_MAX_MEMORY
            
            config = {
                "name": server_id.replace('_', ' ').title(),
                "core_type": core_type,
                "version": version,
                "description": description,
                "memory": {
                    "min": min_memory or DEFAULT_MIN_MEMORY,
                    "max": max_memory or DEFAULT_MAX_MEMORY
                },
                "rcon": {
                    "port": 25575,
                    "auto_password": True
                },
                "created_at": datetime.now().isoformat(),
                "plugins": plugins or []
            }
            
            with open(server_path / 'bot_config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # eula.txt 생성
            with open(server_path / 'eula.txt', 'w') as f:
                f.write("eula=true\n")
            
            return True, f"서버 생성 완료: {server_id}", config
        
        except Exception as e:
            return False, f"서버 생성 오류: {e}", None
    
    async def delete_server(self, server_id: str, force: bool = False) -> Tuple[bool, str]:
        """서버 삭제"""
        try:
            server_path = self.servers_dir / server_id
            
            if not server_path.exists():
                return False, f"서버를 찾을 수 없습니다: {server_id}"
            
            # 백업 생성
            if not force:
                backup_name = f"{server_id}_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                backup_path = self.backups_dir / backup_name
                
                shutil.copytree(server_path, backup_path)
                
                # 백업 메타데이터
                meta = {
                    "server_id": server_id,
                    "deleted_at": datetime.now().isoformat(),
                    "expire_at": (datetime.now() + timedelta(days=30)).isoformat()
                }
                
                with open(backup_path / 'backup_meta.json', 'w') as f:
                    json.dump(meta, f, indent=2)
            
            # 서버 삭제
            shutil.rmtree(server_path)
            
            return True, f"서버 삭제 완료: {server_id}"
        
        except Exception as e:
            return False, f"서버 삭제 오류: {e}"
    
    async def upgrade_server(
        self,
        server_id: str,
        new_version: str,
        new_core_type: Optional[str] = None
    ) -> Tuple[bool, str]:
        """서버 버전 업그레이드"""
        try:
            server_path = self.servers_dir / server_id
            
            if not server_path.exists():
                return False, f"서버를 찾을 수 없습니다: {server_id}"
            
            # 현재 설정 로드
            config_file = server_path / 'bot_config.json'
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            old_core_type = config.get('core_type')
            old_version = config.get('version')
            core_type = new_core_type or old_core_type
            
            # 새 구동기 확인
            new_core_jar = self.core_manager.get_core_path(core_type, new_version)
            if not new_core_jar:
                return False, f"{core_type} {new_version}을 찾을 수 없습니다"
            
            # 백업 생성
            backup_name = f"{server_id}_before_{new_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.backups_dir / backup_name
            
            shutil.copytree(server_path, backup_path)
            
            # 백업 메타데이터
            meta = {
                "server_id": server_id,
                "upgrade_from": f"{old_core_type} {old_version}",
                "upgrade_to": f"{core_type} {new_version}",
                "backup_at": datetime.now().isoformat(),
                "expire_at": (datetime.now() + timedelta(days=30)).isoformat()
            }
            
            with open(backup_path / 'backup_meta.json', 'w') as f:
                json.dump(meta, f, indent=2)
            
            # 구동기 교체
            old_jar = server_path / 'server.jar'
            if old_jar.exists():
                old_jar.unlink()
            
            shutil.copy(new_core_jar, old_jar)
            
            # 설정 업데이트
            config['core_type'] = core_type
            config['version'] = new_version
            config['upgraded_at'] = datetime.now().isoformat()
            config['previous_version'] = f"{old_core_type} {old_version}"
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            return True, f"서버 업그레이드 완료: {old_core_type} {old_version} → {core_type} {new_version}"
        
        except Exception as e:
            return False, f"서버 업그레이드 오류: {e}"
    
    async def rollback_server(self, server_id: str) -> Tuple[bool, str]:
        """서버 롤백"""
        try:
            # 가장 최근 백업 찾기
            backups = sorted([
                b for b in self.backups_dir.iterdir()
                if b.is_dir() and b.name.startswith(server_id)
            ], key=lambda x: x.stat().st_mtime, reverse=True)
            
            if not backups:
                return False, f"백업을 찾을 수 없습니다: {server_id}"
            
            backup_path = backups[0]
            
            # 백업 무결성 검증
            backup_config = backup_path / 'bot_config.json'
            if not backup_config.exists():
                return False, f"백업이 손상되었습니다: bot_config.json 누락"
            
            # 서버 jar 파일 확인
            backup_jar = backup_path / 'server.jar'
            if not backup_jar.exists():
                return False, f"백업이 손상되었습니다: server.jar 누락"
            
            server_path = self.servers_dir / server_id
            
            # 현재 서버 삭제
            if server_path.exists():
                shutil.rmtree(server_path)
            
            # 백업 복원
            shutil.copytree(backup_path, server_path)
            
            # 백업 메타데이터 제거
            meta_file = server_path / 'backup_meta.json'
            if meta_file.exists():
                meta_file.unlink()
            
            return True, f"서버 롤백 완료: {backup_path.name}"
        
        except Exception as e:
            return False, f"서버 롤백 오류: {e}"
    
    async def cleanup_old_backups(self):
        """오래된 백업 삭제"""
        try:
            now = datetime.now()
            deleted = 0
            
            for backup_dir in self.backups_dir.iterdir():
                if not backup_dir.is_dir():
                    continue
                
                meta_file = backup_dir / 'backup_meta.json'
                if not meta_file.exists():
                    continue
                
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                
                expire_at = datetime.fromisoformat(meta.get('expire_at', ''))
                
                if now > expire_at:
                    shutil.rmtree(backup_dir)
                    deleted += 1
            
            return True, f"오래된 백업 {deleted}개 삭제 완료"
        
        except Exception as e:
            return False, f"백업 정리 오류: {e}"
    
    def add_mod_to_server(self, server_id: str, mod_file: Path) -> Tuple[bool, str]:
        """모드 파일 추가"""
        try:
            server_path = self.servers_dir / server_id
            
            if not server_path.exists():
                return False, f"서버를 찾을 수 없습니다: {server_id}"
            
            # bot_config.json 확인
            config_file = server_path / 'bot_config.json'
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            core_type = config.get('core_type')
            
            # 모드 서버인지 확인
            if not self.core_manager.is_modded(core_type):
                return False, f"{core_type}는 모드를 지원하지 않습니다"
            
            # mods 폴더에 복사
            mods_dir = server_path / 'mods'
            mods_dir.mkdir(exist_ok=True)
            
            shutil.copy(mod_file, mods_dir / mod_file.name)
            
            return True, f"모드 추가 완료: {mod_file.name}"
        
        except Exception as e:
            return False, f"모드 추가 오류: {e}"
    
    def add_plugin_to_server(self, server_id: str, plugin_name: str) -> Tuple[bool, str]:
        """플러그인 추가"""
        try:
            server_path = self.servers_dir / server_id
            
            if not server_path.exists():
                return False, f"서버를 찾을 수 없습니다: {server_id}"
            
            # bot_config.json 확인
            config_file = server_path / 'bot_config.json'
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            core_type = config.get('core_type')
            
            # 플러그인 지원 여부 확인
            if not self.core_manager.supports_plugins(core_type):
                return False, f"{core_type}는 플러그인을 지원하지 않습니다"
            
            # 플러그인 JAR 찾기
            plugin_jar = self.core_manager.get_plugin_jar(plugin_name)
            if not plugin_jar:
                return False, f"플러그인을 찾을 수 없습니다: {plugin_name}"
            
            # plugins 폴더에 복사
            plugins_dir = server_path / 'plugins'
            plugins_dir.mkdir(exist_ok=True)
            
            shutil.copy(plugin_jar, plugins_dir / plugin_jar.name)
            
            # 설정 업데이트
            if 'plugins' not in config:
                config['plugins'] = []
            
            if plugin_name not in config['plugins']:
                config['plugins'].append(plugin_name)
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            return True, f"플러그인 추가 완료: {plugin_name}"
        
        except Exception as e:
            return False, f"플러그인 추가 오류: {e}"