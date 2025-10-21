"""
servers/ 폴더에서 마인크래프트 서버 자동 스캔
경로: modules/minecraft/ServerScanner.py
"""

from pathlib import Path
from typing import Dict, List
from .ServerConfigurator import ServerConfigurator


class ServerScanner:
    """서버 폴더 자동 스캔 및 설정"""
    
    def __init__(self, servers_dir: Path, configurator: ServerConfigurator):
        self.servers_dir = servers_dir
        self.configurator = configurator
        self.servers_dir.mkdir(parents=True, exist_ok=True)
    
    def scan_all_servers(self) -> Dict[str, dict]:
        """
        servers/ 폴더의 모든 하위 폴더를 스캔하여 서버 목록 생성
        
        Returns:
            {server_id: server_config, ...}
        """
        print(f"\n🔍 서버 폴더 스캔 중: {self.servers_dir}")
        
        servers = {}
        
        # servers/ 폴더의 모든 하위 디렉토리 스캔
        for folder in self.servers_dir.iterdir():
            if not folder.is_dir():
                continue
            
            # 숨김 폴더 무시
            if folder.name.startswith('.'):
                continue
            
            server_id = folder.name
            
            print(f"\n📁 발견: {server_id}")
            
            # 서버 폴더 검증
            valid, message, info = self.configurator.scan_server_folder(folder)
            
            if not valid:
                print(f"⚠️ 스킵: {message}")
                continue
            
            # 서버 설정 준비
            success, prep_message, server_config = self.configurator.prepare_server(folder)
            
            if not success:
                print(f"❌ 설정 실패: {prep_message}")
                continue
            
            # 서버 ID 추가
            server_config['id'] = server_id
            
            # 시작 명령어 생성
            jar_file = server_config['jar_file']
            min_mem = server_config['memory']['min']
            max_mem = server_config['memory']['max']
            
            server_config['start_command'] = (
                f"java -Xms{min_mem}M -Xmx{max_mem}M "
                f"-jar {jar_file} nogui"
            )
            
            servers[server_id] = server_config
            
            print(f"✅ 등록: {server_id}")
        
        print(f"\n📊 총 {len(servers)}개 서버 발견\n")
        
        return servers
    
    def get_server_summary(self, servers: Dict[str, dict]) -> str:
        """서버 목록 요약 텍스트 생성"""
        if not servers:
            return "등록된 서버가 없습니다."
        
        lines = ["등록된 서버 목록:"]
        for server_id, config in servers.items():
            status = "🆕 신규" if config.get('is_new', False) else "✅ 기존"
            lines.append(
                f"  [{server_id}] {config['name']} - {status}\n"
                f"      메모리: {config['memory']['min']}-{config['memory']['max']}MB, "
                f"포트: {config['port']}"
            )
        
        return "\n".join(lines)