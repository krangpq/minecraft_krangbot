#!/usr/bin/env python3
"""
GCP 환경 자동 설정 스크립트
GCP 메타데이터에서 인스턴스 정보를 자동으로 가져와 config.py 생성
"""

import requests
import json
from pathlib import Path
import sys

# GCP 메타데이터 서버
METADATA_SERVER = "http://metadata.google.internal/computeMetadata/v1"
METADATA_HEADERS = {"Metadata-Flavor": "Google"}

def get_metadata(path: str) -> str:
    """GCP 메타데이터 가져오기"""
    try:
        response = requests.get(
            f"{METADATA_SERVER}/{path}",
            headers=METADATA_HEADERS,
            timeout=2
        )
        if response.status_code == 200:
            return response.text.strip()
        return None
    except:
        return None

def get_gcp_info():
    """GCP 인스턴스 정보 자동 수집"""
    print("🔍 GCP 메타데이터 수집 중...")
    
    # 프로젝트 ID
    project_id = get_metadata("project/project-id")
    
    # 인스턴스 이름
    instance_name = get_metadata("instance/name")
    
    # Zone (전체 경로에서 zone만 추출)
    zone_full = get_metadata("instance/zone")
    zone = zone_full.split('/')[-1] if zone_full else None
    
    # 외부 IP
    external_ip = get_metadata("instance/network-interfaces/0/access-configs/0/external-ip")
    
    # 내부 IP
    internal_ip = get_metadata("instance/network-interfaces/0/ip")
    
    if not all([project_id, instance_name, zone]):
        return None
    
    return {
        "project_id": project_id,
        "instance_name": instance_name,
        "zone": zone,
        "external_ip": external_ip,
        "internal_ip": internal_ip
    }

def create_config_from_template(gcp_info: dict, token: str = None, owner_id: int = None):
    """config.example.py를 기반으로 config.py 생성"""
    
    # config.example.py 읽기
    example_file = Path("config.example.py")
    if not example_file.exists():
        print("❌ config.example.py 파일을 찾을 수 없습니다.")
        return False
    
    with open(example_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # GCP 정보 자동 입력
    replacements = {
        'TOKEN = \'YOUR_DISCORD_BOT_TOKEN_HERE\'': 
            f'TOKEN = \'{token}\'' if token else 'TOKEN = \'YOUR_DISCORD_BOT_TOKEN_HERE\'',
        
        'BOT_OWNER_ID = 0': 
            f'BOT_OWNER_ID = {owner_id}' if owner_id else 'BOT_OWNER_ID = 0',
        
        '"project_id": "your-project-id"': 
            f'"project_id": "{gcp_info["project_id"]}"',
        
        '"name": "minecraft-main-server"': 
            f'"name": "{gcp_info["instance_name"]}"',
        
        '"zone": "asia-northeast3-a"': 
            f'"zone": "{gcp_info["zone"]}"',
        
        'GCP_PROJECT_ID = "your-project-id"': 
            f'GCP_PROJECT_ID = "{gcp_info["project_id"]}"',
        
        'GCP_INSTANCE_NAME = "minecraft-main-server"': 
            f'GCP_INSTANCE_NAME = "{gcp_info["instance_name"]}"',
    }
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    # config.py 저장
    config_file = Path("config.py")
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True

def create_gcp_marker():
    """GCP 환경 마커 파일 생성"""
    marker = Path(".gcp_environment")
    marker.write_text("GCP Environment\n")
    print("✅ .gcp_environment 마커 생성")

def main():
    """메인 실행"""
    print("=" * 60)
    print("🎮 마인크래프트 봇 - GCP 자동 설정")
    print("=" * 60)
    
    # GCP 환경 확인
    gcp_info = get_gcp_info()
    
    if not gcp_info:
        print("\n❌ GCP 메타데이터를 가져올 수 없습니다.")
        print("   이 스크립트는 GCP 인스턴스 내에서만 실행할 수 있습니다.")
        print("\n💡 로컬 환경이라면:")
        print("   1. config.example.py를 config.py로 복사")
        print("   2. 직접 설정 편집")
        sys.exit(1)
    
    # GCP 정보 출력
    print(f"\n✅ GCP 인스턴스 정보:")
    print(f"   프로젝트 ID: {gcp_info['project_id']}")
    print(f"   인스턴스 이름: {gcp_info['instance_name']}")
    print(f"   Zone: {gcp_info['zone']}")
    print(f"   외부 IP: {gcp_info['external_ip']}")
    print(f"   내부 IP: {gcp_info['internal_ip']}")
    
    # 기존 config.py 확인
    if Path("config.py").exists():
        print("\n⚠️ config.py 파일이 이미 존재합니다.")
        choice = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
        if choice != 'y':
            print("❌ 설정 취소")
            sys.exit(0)
    
    # Discord 봇 토큰 입력
    print("\n" + "=" * 60)
    print("📋 Discord 봇 설정")
    print("=" * 60)
    
    token = input("\n디스코드 봇 토큰을 입력하세요 (Enter: 나중에 수동 설정): ").strip()
    if not token:
        token = None
    
    # 봇 소유자 ID 입력
    owner_id_input = input("봇 소유자 Discord ID를 입력하세요 (Enter: 나중에 수동 설정): ").strip()
    owner_id = int(owner_id_input) if owner_id_input.isdigit() else None
    
    # config.py 생성
    print("\n🔧 config.py 생성 중...")
    if create_config_from_template(gcp_info, token, owner_id):
        print("✅ config.py 생성 완료")
    else:
        sys.exit(1)
    
    # .gcp_environment 마커 생성
    create_gcp_marker()
    
    # 요약
    print("\n" + "=" * 60)
    print("🎉 GCP 자동 설정 완료!")
    print("=" * 60)
    
    print(f"\n📋 설정된 정보:")
    print(f"   • 프로젝트: {gcp_info['project_id']}")
    print(f"   • 인스턴스: {gcp_info['instance_name']}")
    print(f"   • Zone: {gcp_info['zone']}")
    print(f"   • 봇 토큰: {'✅ 설정됨' if token else '❌ 수동 설정 필요'}")
    print(f"   • 소유자 ID: {'✅ 설정됨' if owner_id else '❌ 수동 설정 필요'}")
    
    if not token or not owner_id:
        print(f"\n💡 다음 단계:")
        if not token:
            print(f"   1. config.py를 열고 TOKEN을 입력하세요")
        if not owner_id:
            print(f"   2. config.py를 열고 BOT_OWNER_ID를 입력하세요")
    
    print(f"\n🚀 다음 명령어로 봇을 실행하세요:")
    print(f"   python main.py")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()