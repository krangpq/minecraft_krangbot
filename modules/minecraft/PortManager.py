"""
포트 관리 유틸리티
경로: modules/minecraft/PortManager.py
"""

import socket
from typing import Set, Optional


class PortManager:
    """포트 사용 가능 여부 확인 및 자동 할당"""
    
    # 마인크래프트 기본 포트 범위
    DEFAULT_MC_PORT = 25565
    PORT_RANGE_START = 25565
    PORT_RANGE_END = 25600
    
    # RCON 기본 포트 범위
    DEFAULT_RCON_PORT = 25575
    RCON_RANGE_START = 25575
    RCON_RANGE_END = 25650
    
    def __init__(self):
        self.used_ports: Set[int] = set()
    
    @staticmethod
    def is_port_open(port: int, host: str = '0.0.0.0') -> bool:
        """
        포트가 사용 가능한지 확인 (개선된 버전)
        
        Args:
            port: 확인할 포트 번호
            host: 확인할 호스트 (기본: 모든 인터페이스)
        
        Returns:
            True: 포트 사용 가능 (열림)
            False: 포트 사용 중 (닫힘)
        """
        try:
            # bind()로 직접 확인 (가장 정확한 방법)
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_sock.settimeout(1)
            
            try:
                test_sock.bind((host, port))
                test_sock.close()
                return True
            except OSError as e:
                # Address already in use
                test_sock.close()
                return False
                
        except Exception as e:
            print(f"⚠️ 포트 {port} 확인 오류: {e}")
            return False
    
    def find_available_port(self, 
                           start_port: int, 
                           end_port: int, 
                           exclude_ports: Optional[Set[int]] = None) -> Optional[int]:
        """
        사용 가능한 포트 찾기
        
        Args:
            start_port: 시작 포트
            end_port: 끝 포트
            exclude_ports: 제외할 포트 집합
        
        Returns:
            사용 가능한 포트 번호 또는 None
        """
        if exclude_ports is None:
            exclude_ports = set()
        
        # 이미 사용 중인 포트 + 제외할 포트
        all_excluded = self.used_ports | exclude_ports
        
        for port in range(start_port, end_port + 1):
            if port in all_excluded:
                continue
            
            if self.is_port_open(port):
                self.used_ports.add(port)
                return port
        
        return None
    
    def find_minecraft_port(self, prefer_port: Optional[int] = None) -> int:
        """
        마인크래프트 서버용 포트 찾기
        
        Args:
            prefer_port: 선호하는 포트 (가능하면 이 포트 사용)
        
        Returns:
            사용 가능한 포트 번호
        """
        # 선호 포트가 있고 사용 가능하면 사용
        if prefer_port and self.is_port_open(prefer_port):
            self.used_ports.add(prefer_port)
            return prefer_port
        
        # 기본 포트 시도
        if self.is_port_open(self.DEFAULT_MC_PORT) and self.DEFAULT_MC_PORT not in self.used_ports:
            self.used_ports.add(self.DEFAULT_MC_PORT)
            return self.DEFAULT_MC_PORT
        
        # 범위 내에서 찾기
        port = self.find_available_port(self.PORT_RANGE_START, self.PORT_RANGE_END)
        
        if port is None:
            raise RuntimeError(
                f"사용 가능한 마인크래프트 포트를 찾을 수 없습니다 "
                f"({self.PORT_RANGE_START}-{self.PORT_RANGE_END})"
            )
        
        return port
    
    def find_rcon_port(self, mc_port: int, prefer_port: Optional[int] = None) -> int:
        """
        RCON용 포트 찾기
        
        Args:
            mc_port: 마인크래프트 서버 포트 (충돌 방지)
            prefer_port: 선호하는 포트
        
        Returns:
            사용 가능한 포트 번호
        """
        exclude = {mc_port}  # 마인크래프트 포트는 제외
        
        # 선호 포트가 있고 사용 가능하면 사용
        if prefer_port and prefer_port != mc_port and self.is_port_open(prefer_port):
            self.used_ports.add(prefer_port)
            return prefer_port
        
        # 기본 포트 시도
        if (self.DEFAULT_RCON_PORT not in exclude and 
            self.is_port_open(self.DEFAULT_RCON_PORT) and 
            self.DEFAULT_RCON_PORT not in self.used_ports):
            self.used_ports.add(self.DEFAULT_RCON_PORT)
            return self.DEFAULT_RCON_PORT
        
        # 범위 내에서 찾기
        port = self.find_available_port(self.RCON_RANGE_START, self.RCON_RANGE_END, exclude)
        
        if port is None:
            raise RuntimeError(
                f"사용 가능한 RCON 포트를 찾을 수 없습니다 "
                f"({self.RCON_RANGE_START}-{self.RCON_RANGE_END})"
            )
        
        return port
    
    def mark_port_used(self, port: int):
        """포트를 사용 중으로 표시"""
        self.used_ports.add(port)
    
    def release_port(self, port: int):
        """포트 해제"""
        self.used_ports.discard(port)
    
    def get_used_ports(self) -> Set[int]:
        """사용 중인 포트 목록"""
        return self.used_ports.copy()
    
    @staticmethod
    def get_all_listening_ports() -> Set[int]:
        """
        현재 시스템에서 리스닝 중인 모든 포트 찾기
        (선택적 기능 - psutil 필요)
        """
        try:
            import psutil
            listening_ports = set()
            
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr:
                    listening_ports.add(conn.laddr.port)
            
            return listening_ports
        except ImportError:
            # psutil 없으면 빈 set 반환
            return set()
        except Exception as e:
            print(f"⚠️ 리스닝 포트 조회 오류: {e}")
            return set()