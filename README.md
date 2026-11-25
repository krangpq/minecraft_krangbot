# 크랑봇 — 마인크래프트 서버 관리 디스코드 봇

디스코드 슬래시 명령어로 마인크래프트 서버를 켜고 끄고 관리하는 봇입니다.
화이트리스트 + 등급(멤버 / 운영자 / 관리자 / 소유자)으로 명령어 권한을 나눕니다.

## 설치 / 실행

```bash
pip install -r requirements.txt
copy profiles\example.py profiles\prod.py     # TOKEN, BOT_OWNER_ID, SERVERS_DIR 입력
python run_prod.py
```

- 테스트 봇은 `profiles/dev.py` + `python run_dev.py` (토큰을 실제 봇과 분리)
- 테스트: `python tests/run_all.py`
- 친구 등록: 디스코드에서 `/권한 부여` (등급 확인은 `/내권한`)

구조, 설계 규칙, 남은 작업은 [CLAUDE.md](CLAUDE.md)에 있습니다.
이전 GCP + VPN 버전은 태그 `v1-gcp` 입니다.
