# utils.py

"""
유틸리티 함수 모음
경로: utils.py
"""

import discord
from config import BOT_OWNER_ID
import json
from pathlib import Path
from datetime import datetime


def is_authorized(user: discord.User, required_permission: str = "manage_guild") -> bool:
    """
    사용자 권한 확인
    
    Args:
        user: Discord 사용자
        required_permission: 필요한 권한
            - "administrator": 관리자 권한
            - "manage_guild": 서버 관리 권한
            - "manage_channels": 채널 관리 권한
    
    Returns:
        권한이 있으면 True
    """
    # 봇 소유자는 항상 권한 있음
    if user.id == BOT_OWNER_ID:
        return True
    
    # Member 객체가 아니면 권한 확인 불가
    if not isinstance(user, discord.Member):
        return False
    
    # 권한 확인
    if required_permission == "administrator":
        return user.guild_permissions.administrator
    elif required_permission == "manage_guild":
        return user.guild_permissions.manage_guild or user.guild_permissions.administrator
    elif required_permission == "manage_channels":
        return user.guild_permissions.manage_channels or user.guild_permissions.administrator
    
    # 알 수 없는 권한은 거부
    return False


# ============================================
# 🔧 설정 파일 관리 (추가)
# ============================================

class ConfigManager:
    """런타임 설정 파일 자동 생성 및 관리"""
    
    def __init__(self, config_file: str = "bot_runtime_config.json"):
        self.config_file = Path(config_file)
        self.config = self._load_or_create()
    
    def _load_or_create(self) -> dict:
        """설정 파일 로드 또는 기본값 생성"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"✅ 설정 파일 로드: {self.config_file}")
                    self._print_config(config)
                    return config
            except Exception as e:
                print(f"⚠️ 설정 파일 로드 실패: {e}")
                print(f"   기본값으로 초기화합니다.")
        
        # 기본 설정
        default_config = {
            "control_channel_id": None,
            "controller_bot_id": None,
            "enable_gcp_control": False,
            "gcp_instance_name": "minecraft-main-server",
            "created_at": None,
            "updated_at": None
        }
        
        # 파일 생성
        self._save(default_config)
        print(f"✅ 설정 파일 생성: {self.config_file}")
        
        return default_config
    
    def _save(self, config: dict = None):
        """설정 파일 저장"""
        if config is None:
            config = self.config
        
        # 업데이트 시간 기록
        config["updated_at"] = datetime.now().isoformat()
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"💾 설정 저장 완료: {self.config_file}")
        except Exception as e:
            print(f"❌ 설정 저장 실패: {e}")
    
    def _print_config(self, config: dict):
        """설정 내용 출력"""
        print(f"   📋 제어 채널 ID: {config.get('control_channel_id')}")
        print(f"   🤖 컨트롤러 봇 ID: {config.get('controller_bot_id')}")
        print(f"   🔧 GCP 제어: {'✅' if config.get('enable_gcp_control') else '❌'}")
    
    def get(self, key: str, default=None):
        """설정값 가져오기"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """설정값 변경 및 저장"""
        self.config[key] = value
        self._save()
    
    def update(self, **kwargs):
        """여러 설정값 한 번에 변경"""
        self.config.update(kwargs)
        self._save()
    
    def reset(self):
        """설정 초기화"""
        self.config = {
            "control_channel_id": None,
            "controller_bot_id": None,
            "enable_gcp_control": False,
            "gcp_instance_name": "minecraft-main-server",
            "created_at": None,
            "updated_at": None
        }
        self._save()
        print(f"🔄 설정 초기화 완료")
    
    def export_summary(self) -> str:
        """설정 요약 텍스트"""
        lines = [
            "📋 **현재 설정**",
            f"• 제어 채널 ID: `{self.get('control_channel_id') or '미설정'}`",
            f"• 컨트롤러 봇 ID: `{self.get('controller_bot_id') or '미설정'}`",
            f"• GCP 제어: {'✅ 활성화' if self.get('enable_gcp_control') else '❌ 비활성화'}",
            f"• GCP 인스턴스: `{self.get('gcp_instance_name') or '미설정'}`",
        ]
        
        if self.get('created_at'):
            lines.append(f"• 생성 시각: `{self.get('created_at')}`")
        if self.get('updated_at'):
            lines.append(f"• 수정 시각: `{self.get('updated_at')}`")
        
        return "\n".join(lines)


# utils.py에 추가
import logging
from pathlib import Path

def setup_logger(name: str, log_dir: Path):
    """로거 설정"""
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러
    file_handler = logging.FileHandler(
        log_dir / f"{name}.log",
        encoding='utf-8'
    )
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    )
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(message)s')
    )
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger