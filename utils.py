# utils.py

"""
유틸리티 함수 모음
경로: utils.py

(권한 확인은 modules/permissions 로, GCP 런타임 설정(ConfigManager)은 GCP 제거와 함께 삭제)
"""

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