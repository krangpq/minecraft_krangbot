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
        게임 포트는 server.properties 값을 그대로 쓰고, 없을 때만 새로 할당합니다.
        
        Returns:
            {server_id: server_config, ...}
        """
        print(f"\n🔍 서버 폴더 스캔 중: {self.servers_dir}")
        
        servers = {}
        
        # 1차: server.properties 에 적힌 게임 포트를 먼저 전부 예약
        declared_ports = {}
        duplicated_ports = {}
        for folder in self.servers_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith('.'):
                continue
            port = self.configurator.read_declared_port(folder)
            if port is not None:
                declared_ports[folder.name] = port
                duplicated_ports[port] = duplicated_ports.get(port, 0) + 1
                self.port_manager.mark_port_used(port)
        
        # 2차: servers/ 폴더의 모든 하위 디렉토리 스캔
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
            
            # ===== 포트 =====
            # 게임 포트: server.properties에 적혀 있으면 절대 안 바꿈 (공유기 포트포워딩과 어긋나지 않게)
            #           → 봇 재시작 때 서버가 이미 켜져 있어서 포트가 "사용 중"이어도 그대로 둠
            # 적혀 있지 않은 새 서버만 빈 포트를 골라서 기록
            existing_port = declared_ports.get(folder.name)
            
            if existing_port is not None:
                mc_port = existing_port
                server_config['port'] = mc_port
                if not self.port_manager.is_port_open(mc_port):
                    print(f"   ℹ️ 마인크래프트 포트 {mc_port}: 지금 사용 중 (이미 켜져 있거나 다른 프로그램) — 포트는 그대로 둡니다")
                else:
                    print(f"   ✅ 마인크래프트 포트: {mc_port} (server.properties 고정)")
                if duplicated_ports.get(mc_port, 0) > 1:
                    print(f"   ⚠️ 포트 {mc_port} 를 다른 서버도 쓰고 있어요 — 둘을 동시에 켤 수 없습니다")
            else:
                try:
                    mc_port = self.port_manager.find_minecraft_port()
                    server_config['port'] = mc_port
                    self.configurator.set_server_port(folder, mc_port)
                    print(f"   🆕 마인크래프트 포트: {mc_port} 할당 → server.properties 기록 (포트포워딩 추가 필요)")
                except RuntimeError as e:
                    print(f"   ❌ 포트 할당 실패: {e}")
                    print(f"   💡 사용 가능한 포트 범위: {self.port_manager.PORT_RANGE_START}-{self.port_manager.PORT_RANGE_END}")
                    print(f"   💡 다른 서버를 중지하거나 포트를 수동 설정하세요")
                    continue
            
            # RCON 포트: 봇만 localhost로 쓰는 포트라 바뀌어도 상관없음 (포워딩 금지)
            try:
                rcon_port = server_config.get('rcon', {}).get('port', PortManager.DEFAULT_RCON_PORT)
                new_rcon_port = self.port_manager.find_rcon_port(
                    mc_port=mc_port,
                    prefer_port=rcon_port
                )
                server_config['rcon']['port'] = new_rcon_port
                print(f"   ✅ RCON 포트: {new_rcon_port}")
                
                # RCON 설정 업데이트
                rcon_password = server_config['rcon']['password']
                self.configurator.setup_rcon(folder, new_rcon_port, rcon_password)
                
                # 포트가 바뀌었으면 bot_config.json 에도 반영 (다음 시작 때 또 옮기지 않게)
                if new_rcon_port != rcon_port:
                    bot_config = self.configurator.load_bot_config(folder)
                    bot_config.setdefault('rcon', {})['port'] = new_rcon_port
                    self.configurator.save_bot_config(folder, bot_config)
                
            except RuntimeError as e:
                print(f"   ❌ RCON 포트 할당 실패: {e}")
                print(f"   💡 사용 가능한 RCON 포트 범위: {self.port_manager.RCON_RANGE_START}-{self.port_manager.RCON_RANGE_END}")
                # RCON 실패해도 서버는 등록 (RCON 비활성화)
                server_config['rcon']['enabled'] = False
            
            # ===== 포트 끝 =====
            
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