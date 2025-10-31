"""
servers/ 폴더에서 마인크래프트 서버 자동 스캔
경로: modules/minecraft/ServerScanner.py
"""

from pathlib import Path
from typing import Dict
from .ServerConfigurator import ServerConfigurator
from .PortManager import PortManager


class ServerScanner:
    """서버 폴더 자동 스캔 및 설정"""
    
    def __init__(self, servers_dir: Path, configurator: ServerConfigurator):
        self.servers_dir = servers_dir
        self.configurator = configurator
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        
        # 포트 관리자 초기화
        self.port_manager = PortManager()
        
        # 시스템에서 이미 리스닝 중인 포트 확인
        listening_ports = self.port_manager.get_all_listening_ports()
        if listening_ports:
            print(f"🔍 현재 사용 중인 포트: {len(listening_ports)}개")
    
    def get_server_summary(self, servers: Dict[str, dict]) -> str:
        """서버 목록 요약 텍스트 생성"""
        if not servers:
            return "등록된 서버가 없습니다."
        
        lines = ["등록된 서버 목록:"]
        for server_id, config in servers.items():
            status = "🆕 신규" if config.get('is_new', False) else "✅ 기존"
            rcon_port = config.get('rcon', {}).get('port', 'N/A')
            lines.append(
                f"  [{server_id}] {config['name']} - {status}\n"
                f"      메모리: {config['memory']['min']}-{config['memory']['max']}MB\n"
                f"      포트: {config['port']} (MC) | {rcon_port} (RCON)"
            )
        
        return "\n".join(lines)
    
    def scan_all_servers(self) -> Dict[str, dict]:
        """
        servers/ 폴더의 모든 하위 폴더를 스캔하여 서버 목록 생성
        포트는 자동으로 할당됩니다.
        
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
            
            # ===== 포트 자동 할당 =====
            
            # 1. server.properties에서 기존 포트 읽기
            existing_port = self.configurator.get_server_port(folder)
            
            # 2. 마인크래프트 포트 할당
            try:
                # 기존 포트가 사용 가능하면 그대로 사용
                mc_port = self.port_manager.find_minecraft_port(prefer_port=existing_port)
                server_config['port'] = mc_port
                print(f"   ✅ 마인크래프트 포트: {mc_port}")
            except RuntimeError as e:
                print(f"   ❌ 포트 할당 실패: {e}")
                print(f"   💡 사용 가능한 포트 범위: {self.port_manager.PORT_RANGE_START}-{self.port_manager.PORT_RANGE_END}")
                print(f"   💡 다른 서버를 중지하거나 포트를 수동 설정하세요")
                continue
            
            # 3. RCON 포트 할당
            try:
                rcon_port = server_config.get('rcon', {}).get('port', 25575)
                new_rcon_port = self.port_manager.find_rcon_port(
                    mc_port=mc_port,
                    prefer_port=rcon_port
                )
                server_config['rcon']['port'] = new_rcon_port
                print(f"   ✅ RCON 포트: {new_rcon_port}")
                
                # RCON 설정 업데이트
                rcon_password = server_config['rcon']['password']
                self.configurator.setup_rcon(folder, new_rcon_port, rcon_password)
                
            except RuntimeError as e:
                print(f"   ❌ RCON 포트 할당 실패: {e}")
                print(f"   💡 사용 가능한 RCON 포트 범위: {self.port_manager.RCON_RANGE_START}-{self.port_manager.RCON_RANGE_END}")
                # RCON 실패해도 서버는 등록 (RCON 비활성화)
                server_config['rcon']['enabled'] = False
            
            # ===== 포트 할당 끝 =====
            
            # server.properties에 할당된 포트 저장
            if mc_port != existing_port:
                self.configurator.set_server_port(folder, mc_port)
                print(f"   📝 server.properties 업데이트: 포트 {mc_port}")
            
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