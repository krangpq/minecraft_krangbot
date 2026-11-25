"""
마인크래프트 서버 자동 설정 및 초기화
경로: modules/minecraft/ServerConfigurator.py
"""

import json
import os
import secrets
import re
from pathlib import Path
from typing import Tuple, Optional

from .PortManager import PortManager
from . import LaunchResolver


class ServerConfigurator:
    """서버 자동 설정 관리"""
    
    BOT_CONFIG_FILE = "bot_config.json"
    
    def __init__(self, default_min_memory: int, default_max_memory: int):
        """
        Args:
            default_min_memory: 기본 최소 메모리 (MB)
            default_max_memory: 기본 최대 메모리 (MB)
        """
        self.default_min_memory = default_min_memory
        self.default_max_memory = default_max_memory
    
    def scan_server_folder(self, server_path: Path) -> Tuple[bool, str, Optional[dict]]:
        """
        서버 폴더를 스캔하여 정보 수집 (파일은 안 고침)
        실행 방법(Forge/NeoForge args 파일, 일반 jar, bot_config 의 launch)이 있어야 유효

        Returns:
            (유효한 폴더인지, 메시지, 서버 정보)
        """
        if not server_path.exists():
            return False, "폴더가 존재하지 않습니다.", None

        if not server_path.is_dir():
            return False, "폴더가 아닙니다.", None

        bot_config = self.read_bot_config(server_path)
        plan, why = LaunchResolver.resolve_launch(
            server_path, bot_config, self.default_min_memory, self.default_max_memory)
        if plan is None:
            return False, why, None

        level_name = self.read_properties(server_path).get("level-name") or "world"
        info = {
            "launch": plan,
            "launch_message": why,
            "jar_file": plan.jar_file,
            "has_world": (server_path / level_name).exists(),
            "has_eula": (server_path / "eula.txt").exists(),
            "has_properties": (server_path / "server.properties").exists(),
            "has_bot_config": (server_path / self.BOT_CONFIG_FILE).exists()
        }

        return True, "서버 폴더가 유효합니다.", info

    @classmethod
    def read_bot_config(cls, server_path: Path) -> dict:
        """bot_config.json 읽기만 (없거나 깨졌으면 빈 dict)"""
        config_file = server_path / cls.BOT_CONFIG_FILE
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def read_properties(server_path: Path) -> dict:
        """server.properties → dict (없으면 빈 dict)"""
        out = {}
        try:
            for line in (server_path / "server.properties").read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
        except OSError:
            pass
        return out

    def load_bot_config(self, server_path: Path, include_memory: bool = True,
                        memory: Optional[Tuple[int, int]] = None) -> dict:
        """
        bot_config.json 로드 (없으면 기본값 생성)
        include_memory=False: Forge/NeoForge 서버팩 — 메모리는 user_jvm_args.txt 에서만 관리하므로 안 넣음

        Returns:
            서버 설정 딕셔너리
        """
        config_file = server_path / self.BOT_CONFIG_FILE

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if not isinstance(config, dict):
                    raise ValueError("JSON 객체가 아님")
                config.setdefault("rcon", {})
                print(f"✅ 봇 설정 로드: {server_path.name}")
                return config
            except Exception as e:
                print(f"⚠️ 봇 설정 로드 실패, 기본값 사용 (파일은 그대로 둠): {e}")
                return self._default_bot_config(include_memory, memory)

        config = self._default_bot_config(include_memory, memory)
        self.save_bot_config(server_path, config)
        print(f"✅ 봇 설정 생성: {server_path.name}")

        return config

    def _default_bot_config(self, include_memory: bool, memory: Optional[Tuple[int, int]] = None) -> dict:
        config = {}
        if include_memory:
            mn, mx = memory if memory and memory[1] else (self.default_min_memory, self.default_max_memory)
            config["memory"] = {"min": mn, "max": mx}
        config["rcon"] = {"port": PortManager.DEFAULT_RCON_PORT, "auto_password": True}
        config["description"] = ""
        return config

    def save_bot_config(self, server_path: Path, config: dict):
        """bot_config.json 저장 (임시 파일 → os.replace, 전원 차단 대비)"""
        config_file = server_path / self.BOT_CONFIG_FILE
        tmp = config_file.with_name(config_file.name + ".tmp")
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, config_file)
        except Exception as e:
            print(f"❌ 봇 설정 저장 실패: {e}")

    def generate_rcon_password(self, length: int = 16) -> str:
        """
        안전한 RCON 비밀번호 생성 (개선된 버전)
        일부 마인크래프트 버전에서 특수문자 처리 문제가 있어 알파벳+숫자만 사용
        """
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password
    
    def setup_eula(self, server_path: Path) -> Tuple[bool, str]:
        """
        eula.txt 자동 설정
        
        Returns:
            (성공 여부, 메시지)
        """
        eula_file = server_path / "eula.txt"
        
        try:
            if eula_file.exists():
                with open(eula_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'eula=true' in content:
                    return True, "EULA가 이미 동의되어 있습니다."
                
                content = re.sub(r'eula=false', 'eula=true', content)
            else:
                content = (
                    "# By changing the setting below to TRUE you are indicating your agreement to our EULA (https://aka.ms/MinecraftEULA).\n"
                    "# Generated by Discord Bot\n"
                    "eula=true\n"
                )
            
            with open(eula_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ EULA 동의 완료: {server_path.name}")
            return True, "EULA가 자동으로 동의되었습니다."
            
        except Exception as e:
            print(f"❌ EULA 설정 실패: {e}")
            return False, f"EULA 설정 오류: {e}"
    
    def setup_rcon(self, server_path: Path, rcon_port: int, rcon_password: str) -> Tuple[bool, str]:
        """
        server.properties에 RCON 설정 추가/수정
        
        Returns:
            (성공 여부, 메시지)
        """
        properties_file = server_path / "server.properties"
        
        try:
            if properties_file.exists():
                with open(properties_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            else:
                lines = []
            
            rcon_settings = {
                'enable-rcon': 'true',
                'rcon.port': str(rcon_port),
                'rcon.password': rcon_password
            }
            
            updated_lines = []
            found_keys = set()
            
            for line in lines:
                line = line.strip()
                
                if not line or line.startswith('#'):
                    updated_lines.append(line)
                    continue
                
                if '=' in line:
                    key = line.split('=')[0].strip()
                    
                    if key in rcon_settings:
                        updated_lines.append(f"{key}={rcon_settings[key]}")
                        found_keys.add(key)
                    else:
                        updated_lines.append(line)
                else:
                    updated_lines.append(line)
            
            if not found_keys:
                updated_lines.append("")
                updated_lines.append("# RCON Settings (Auto-generated by Bot)")
            
            for key, value in rcon_settings.items():
                if key not in found_keys:
                    updated_lines.append(f"{key}={value}")
            
            with open(properties_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_lines) + '\n')  # 끝 줄바꿈 (다른 함수가 이어 붙여도 안 깨지게)
            
            print(f"✅ RCON 설정 완료: {server_path.name}")
            return True, f"RCON이 포트 {rcon_port}에 설정되었습니다."
            
        except Exception as e:
            print(f"❌ RCON 설정 실패: {e}")
            return False, f"RCON 설정 오류: {e}"
    
    def read_declared_port(self, server_path: Path) -> Optional[int]:
        """
        server.properties 에 server-port 가 실제로 적혀 있으면 그 값, 없거나 못 읽으면 None
        (get_server_port 는 없을 때 25565 를 돌려줘서 '적혀 있음'과 구분이 안 됨)
        """
        properties_file = server_path / "server.properties"
        if not properties_file.exists():
            return None
        try:
            with open(properties_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('server-port='):
                        value = line.split('=', 1)[1].strip()
                        if value.isdigit() and 1 <= int(value) <= 65535:
                            return int(value)
                        return None
        except OSError as e:
            print(f"⚠️ server.properties 읽기 실패 ({server_path.name}): {e}")
        return None
    
    def get_server_port(self, server_path: Path) -> int:
        """server.properties에서 포트 읽기"""
        properties_file = server_path / "server.properties"
        
        if not properties_file.exists():
            return 25565  # 기본 포트
        
        try:
            with open(properties_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('server-port='):
                        port = line.split('=')[1].strip()
                        return int(port)
        except:
            pass
        
        return 25565  # 기본 포트
    
    def set_server_port(self, server_path: Path, port: int) -> Tuple[bool, str]:
        """
        server.properties에 포트 설정
        
        Args:
            server_path: 서버 경로
            port: 설정할 포트 번호
        
        Returns:
            (성공 여부, 메시지)
        """
        properties_file = server_path / "server.properties"
        
        try:
            if properties_file.exists():
                with open(properties_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            else:
                lines = []
            
            updated_lines = []
            port_found = False
            
            for line in lines:
                stripped = line.strip()
                
                if stripped.startswith('server-port='):
                    updated_lines.append(f"server-port={port}\n")
                    port_found = True
                else:
                    updated_lines.append(line)
            
            if not port_found:
                # 마지막 줄에 줄바꿈이 없으면 붙어버림 (예: rcon.password=XXXserver-port=25566)
                if updated_lines and not updated_lines[-1].endswith('\n'):
                    updated_lines[-1] += '\n'
                updated_lines.append(f"server-port={port}\n")
            
            with open(properties_file, 'w', encoding='utf-8') as f:
                f.writelines(updated_lines)
            
            return True, f"포트가 {port}로 설정되었습니다."
            
        except Exception as e:
            return False, f"포트 설정 오류: {e}"
    
    def _read_rcon_password(self, server_path: Path) -> Optional[str]:
        """
        server.properties에서 기존 RCON 비밀번호 읽기
        
        Returns:
            기존 비밀번호 또는 None
        """
        properties_file = server_path / "server.properties"
        
        if not properties_file.exists():
            return None
        
        try:
            with open(properties_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('rcon.password='):
                        password = line.split('=', 1)[1].strip()
                        if password:
                            return password
        except Exception as e:
            print(f"⚠️ RCON 비밀번호 읽기 실패: {e}")
        
        return None
    
    def prepare_server(self, server_path: Path, running_record: Optional[dict] = None) -> Tuple[bool, str, dict]:
        """
        서버 실행 전 설정 자동화 (eula, RCON, bot_config.json)

        running_record: 이 서버가 지금 켜져 있으면 PID 파일 내용 (외부 실행이면 external=True)
            → 켜져 있는 서버의 파일은 건드리지 않고, 실행 당시 RCON 설정을 그대로 씀
              (바꾸면 켜져 있는 서버와 봇 설정이 어긋나서 RCON 이 안 됨)

        Returns:
            (성공 여부, 메시지, 서버 설정)
        """
        print(f"\n🔧 서버 설정 중: {server_path.name}")

        valid, message, info = self.scan_server_folder(server_path)
        if not valid:
            return False, message, {}

        plan = info['launch']
        print(f"   🚀 실행 방식: {plan.describe()} ({info['launch_message']})")
        for w in plan.warnings:
            print(f"   ⚠️ {w}")

        running = running_record is not None

        if running:
            bot_config = self.read_bot_config(server_path)
            bot_config.setdefault("rcon", {})
            props = self.read_properties(server_path)
            rcon_enabled = props.get("enable-rcon", "false").lower() == "true"
            rcon_port = None
            if running_record.get("rcon_port") and not running_record.get("external"):
                rcon_enabled = bool(running_record.get("rcon_enabled", True))
                rcon_port = int(running_record["rcon_port"])
            if rcon_port is None:
                try:
                    rcon_port = int(props.get("rcon.port", PortManager.DEFAULT_RCON_PORT))
                except ValueError:
                    rcon_port = PortManager.DEFAULT_RCON_PORT
            rcon_password = props.get("rcon.password", "")
            if rcon_enabled and not rcon_password:
                rcon_enabled = False
            rcon_text = f"포트 {rcon_port}" if rcon_enabled else "없음 (다음에 봇으로 켤 때 설정)"
            print(f"   ▶️ 실행 중 → 파일 안 고침, RCON {rcon_text}")
        else:
            uses_bot_memory = plan.kind in ("jar", "fabric")
            bot_config = self.load_bot_config(
                server_path, include_memory=uses_bot_memory,
                memory=(plan.memory_min_mb, plan.memory_max_mb) if uses_bot_memory else None)

            success, eula_msg = self.setup_eula(server_path)
            if not success:
                return False, eula_msg, {}

            rcon_port = bot_config['rcon'].get('port', PortManager.DEFAULT_RCON_PORT)

            existing_password = self._read_rcon_password(server_path)

            if existing_password:
                rcon_password = existing_password
                print(f"   🔑 기존 RCON 비밀번호 사용")
            elif bot_config['rcon'].get('auto_password', True):
                rcon_password = self.generate_rcon_password()
                print(f"   🔑 새 RCON 비밀번호 생성")
            else:
                rcon_password = bot_config['rcon'].get('password', self.generate_rcon_password())
                print(f"   🔑 설정된 RCON 비밀번호 사용")

            success, rcon_msg = self.setup_rcon(server_path, rcon_port, rcon_password)
            if not success:
                return False, rcon_msg, {}
            rcon_enabled = True

        server_port = self.get_server_port(server_path)

        server_config = {
            "name": bot_config.get("name") or server_path.name.replace('_', ' ').title(),
            "path": str(server_path),
            "jar_file": info['jar_file'],
            "launch_kind": plan.kind,
            "launch_args": plan.args,
            "mc_version": plan.mc_version,
            "memory": {
                "min": plan.memory_min_mb,
                "max": plan.memory_max_mb,
                "source": plan.memory_source,
            },
            "port": server_port,
            "rcon": {
                "enabled": rcon_enabled,
                "host": "localhost",
                "port": rcon_port,
                "password": rcon_password
            },
            "description": bot_config.get('description', ''),
            "is_new": not info['has_world'],
            "running_at_scan": running,
        }

        print(f"✅ 서버 설정 완료: {server_path.name}")
        mem = server_config['memory']
        print(f"   - 메모리: {mem['min'] or '?'}MB ~ {mem['max'] or '?'}MB ({mem['source'] or '알 수 없음'})")

        return True, "서버 설정이 완료되었습니다.", server_config
