# CLAUDE.md — 크랑봇 (마인크래프트 서버 관리 디스코드 봇)

친구들이 디스코드 슬래시 명령어로 마인크래프트 서버를 켜고 끄고 관리하는 봇.
원래 GCP(게임 서버) + VPN 서버(GCP 제어용 컨트롤러 봇) 구조였고, **본가 Windows 데스크톱 단독 운영으로 재구성 중**이다.

- 이전 GCP 버전: 태그 `v1-gcp`
- 현재: 데스크톱 재구성 **1단계 완료** (권한 등급, GCP 제거, 실행 파일 분리, 포트 고정) → **다음은 2단계** (아래 "다음 작업")

## 빠른 시작

```bash
pip install -r requirements.txt
python tests/run_all.py                 # 디스코드 접속 없이 전체 테스트 (커밋 전 필수)

copy profiles\example.py profiles\dev.py   # (Linux/mac: cp) TOKEN, BOT_OWNER_ID, SERVERS_DIR, DEV_GUILD_ID 채우기
python run_dev.py                       # 테스트 봇
python run_prod.py                      # 실제 운영 봇 (profiles/prod.py)
```

`bot.py` 를 직접 실행하면 안 된다 (프로필이 안 불러와져서 멈춤).

## 구조

```
run_prod.py / run_dev.py   진입 파일. settings.activate("prod"|"dev") 후 bot.main()
settings.py                공통 기본값 + 프로필 로더 (profiles/<이름>.py 값으로 덮어씀)
profiles/example.py        프로필 템플릿 (prod.py, dev.py 는 gitignore — 토큰 들어감)
bot.py                     MinecraftBot (commands.Bot, tree_cls=PermissionTree), 빈 서버 자동 종료 루프
utils.py                   setup_logger 만 남음
modules/permissions/       화이트리스트 + 등급 권한
  PermissionTable.py         등급 정의, 명령어→필요 등급 표, 옵션별 등급, 조사(josa) 헬퍼
  PermissionManager.py       data/<프로필>/permissions.json 저장·부여·회수 규칙
  PermissionTree.py          모든 명령어 앞단 게이트(interaction_check) + 권한표 점검
  PermissionCommands.py      /권한 부여·회수·목록, /내권한
modules/minecraft/
  ServerScanner.py           SERVERS_DIR 하위 폴더 = 서버 하나씩 스캔, 포트 결정
  ServerConfigurator.py      eula, server.properties(포트·RCON), bot_config.json
  PortManager.py             포트 검사/할당 (게임 25565-25600, RCON 35575-35650)
  ServerManager.py           시작/중지/상태/명령/백업 (⚠️ Windows 미완, 아래 참고)
  ScreenManager.py           Linux screen + OS별 TerminalLauncher (Windows 부분이 문제)
  ServerCoreManager.py       Paper/Vanilla/Fabric/Forge 구동기·플러그인 다운로드, Spigot 빌드
  ServerLifecycleManager.py  서버 생성/삭제/업그레이드/롤백, 백업 30일 보관
  ServerCommands.py, ServerLifecycleCommands.py   슬래시 명령어
  RconClient.py              mcrcon 래퍼
tests/                     run_all.py, test_permissions.py, test_integration.py
```

## 설정 (settings.py + profiles)

- 진입 파일이 `settings.activate()` 를 **먼저** 호출하고 그 다음에 봇 모듈을 import 한다. 그래서 다른 모듈은 그냥 `from settings import X` 로 쓴다.
- 프로필 파일은 import 가 아니라 소스를 직접 `exec` 한다 (.pyc 캐시 때문에 옛 값이 로드되던 문제 + 토큰 든 .pyc 가 남는 문제 방지). importlib 로 되돌리지 말 것.
- 프로필에 settings.py 에 없는 이름을 쓰면 오타로 보고 시작을 멈춘다. **새 설정은 settings.py 에 기본값부터 추가**.
- `DEV_GUILD_ID` 가 있으면 그 길드에만 명령어 동기화(즉시 반영), 없으면 전역 동기화.
- `UPDATE_CORES_ON_START=False` 기본. 구동기가 없으면 `/서버생성` 전에 `/구동기업데이트` 필요.
- 환경 감지는 OS(`platform.system()`)만 한다. 예전 GCP 메타데이터 소켓 감지 같은 건 다시 넣지 말 것.

## 권한 시스템 (화이트리스트 + 등급)

| 등급 | 값 | 쓸 수 있는 것 |
|---|---|---|
| 미등록 | 0 | `/내아이디`, `/내권한` |
| 멤버 | 1 | 조회 (서버상태, 서버목록, 구동기목록 …) |
| 운영자 | 2 | 서버시작/중지/재시작, 백업 |
| 관리자 | 3 | 명령어실행, 서버생성/업그레이드/롤백, 모드·플러그인 추가, 구동기업데이트, 백업정리, 권한 부여·회수·목록 |
| 소유자 | 4 | 전부 + 서버삭제. 프로필 `BOT_OWNER_ID` 로만 정해짐 |

규칙
- **명령어 권한은 `PermissionTable.COMMAND_LEVELS` 한 곳에서만** 정한다. 명령어 함수 안에서 권한을 따로 검사하지 말 것 (예전 `bot.is_authorized` 방식은 제거됨).
- **새 슬래시 명령어를 추가하면 반드시 표에 넣는다.** 안 넣으면 소유자 전용으로 막히고 봇 시작 시 `[권한] ⚠️ 권한표에 없는 명령어` 경고가 뜬다. 그룹 하위 명령어 키는 `"그룹 하위명"` (예: `"권한 부여"`).
- 옵션에 따라 등급을 올릴 땐 `OPTION_LEVELS` (현재 `/서버중지 강제` → 관리자).
- 자기보다 낮은 등급만 부여/회수, 자기 자신·소유자·봇 계정은 대상 불가. 부여/회수 자체에 필요한 등급도 표(`권한 부여`, `권한 회수`)를 따름.
- 디스코드 역할(role)/서버 권한은 **의도적으로** 안 본다 (디스코드 관리자가 역할로 화이트리스트를 우회하는 걸 막기 위해).
- 저장은 임시 파일 → `os.replace` (전원 차단 대비). 파일이 깨지면 `.corrupt-날짜` 로 옮기고 빈 목록 = 소유자만 사용 (fail-closed).
- 자동완성도 같은 기준으로 막힌다 (권한 없으면 빈 목록).

## 포트 정책 (공유기 포트포워딩 사용 중)

- **게임 포트는 server.properties 에 적힌 값을 봇이 절대 바꾸지 않는다.** 사용 중이어도 그대로 둔다 (포워딩 규칙과 어긋나지 않게). 포트가 없는 새 서버만 빈 포트를 골라 기록한다.
- 같은 게임 포트를 쓰는 서버가 둘이면 경고만 (동시 실행 불가).
- **RCON 은 35575-35650**, 게임 포트 범위와 겹치지 않게 분리. 봇만 localhost 로 쓰고 **포워딩 금지**. 예전 기본값(25575)처럼 게임 범위에 있으면 자동으로 옮기고 bot_config.json 에도 반영.
- `PortManager.is_port_open` 은 Windows 에서 `SO_REUSEADDR` 를 안 쓴다 (Windows 에선 사용 중 포트에도 bind 를 허용해서 검사가 무의미해짐). **실제 Windows 에서 아직 검증 안 함.**
- server.properties 를 쓸 땐 끝 줄바꿈 유지 (예전에 줄바꿈 없이 이어 붙여서 `rcon.password=XXXserver-port=25566` 처럼 깨진 버그가 있었음).

## 운영 환경 (설계 전제)

- 운영: 본가 Windows 데스크톱 (Ryzen 7 9700X, RAM 32GB). 원격으로 관리하며, 다른 무거운 CPU 작업과 같이 돌 수 있음 → 모드팩 서버 동시 실행 수는 RAM 기준으로 보수적으로.
- **갑자기 전원이 나갈 수 있다** (불안정 시 스마트 플러그로 재부팅). 파일 쓰기는 원자적으로, 봇·서버는 재부팅 후 스스로 복구하는 것을 전제로 설계.
- 소유자가 오래 자리를 비울 수 있다 → 무인 운영, 친구들은 등급 권한으로 직접 켜고 끈다.
- 서버 폴더: `C:\mcserver\<서버>` (모드팩 위주, 예: Cursed Jujutsu 모드팩 = Forge 1.20.1). **실제 폴더 구조는 아직 확인 안 함** → 2단계 시작 전에 확인.
- 개발: 노트북에서 `run_dev.py` (별도 테스트 봇 토큰 + `DEV_GUILD_ID`).
- 디스코드 레이트 리밋: 로그/상태 패널은 새 메시지를 계속 보내지 말고 기존 메시지를 수정.
- **출력 인코딩**: Windows 에서 출력을 파일·파이프로 돌리면(서비스, 작업 스케줄러) Python 3.15 미만은 cp949 로 인코딩해서 이모지 `print` 에서 `UnicodeEncodeError` 로 죽는다. `run_prod.py`/`run_dev.py` 맨 위에서 stdout/stderr 를 UTF-8 로 고정해 뒀음 → 새 진입 파일을 만들면 같은 처리를 넣을 것. 하위 프로세스는 `-X utf8`.

## 다음 작업 (우선순위 순)

### 2단계 — Windows 프로세스 관리 (핵심, 이게 안 되면 서버 켜기/끄기가 Windows 에서 사실상 안 됨)
1. **Windows 에서 실행한 서버가 추적되지 않는다.** `ServerManager.start_server` → `TerminalLauncher.launch_server` → `_launch_windows` 가 세션/프로세스를 돌려주지 않아 `running_servers` 에 등록이 안 됨 → `is_server_running` 이 항상 False → 상태 표시·중지·빈 서버 자동 종료가 다 안 먹고, 다시 켜면 중복 실행을 시도함.
   - 기본 모드 `separate` 는 `start ... cmd /k` 로 새 창만 띄움 (핸들 없음).
   - `TerminalLauncher._launch_background` 는 `stdout=PIPE` 를 읽지 않음 (파이프가 차면 서버가 멈출 수 있음) + 역시 등록 안 됨.
   - `ServerManager._start_background` (로그 파일로 stdout, Popen 등록) 는 terminal_launcher 가 없을 때만 쓰임.
   - 방향: java 를 직접 실행(작업 디렉터리 = 서버 폴더, 로그는 파일) → **PID 파일**(서버 폴더 또는 data/) 기록 → 봇 재시작 시 **psutil 로 PID+명령줄 검증해서 재연결** → 명령·정지는 RCON(`stop`), 콘솔 로그는 `logs/latest.log` 추적. 봇이 죽어도 서버는 살아 있게 (봇 프로세스와 분리, Windows 는 `CREATE_NEW_PROCESS_GROUP`/`DETACHED_PROCESS` 검토).
   - `_reconnect_existing_servers` 는 지금 Linux screen 전용.
2. **모드팩 실행 방식 인식.** 스캐너는 `*.jar`(server.jar 우선)를 골라 `java -Xms -Xmx -jar X nogui` 로 실행함. Forge 1.17+ / NeoForge 서버팩은 `run.bat` + `user_jvm_args.txt` + `libraries/net/minecraftforge/forge/<ver>/win_args.txt` (NeoForge 는 `libraries/net/neoforged/neoforge/<ver>/win_args.txt`) 구조라 루트에 실행할 jar 가 없거나 installer jar 를 잡을 수 있음.
   - 방향: 감지 순서 = bot_config.json 의 명시적 시작 명령 → Forge/NeoForge args 파일 → 일반 jar. 메모리(-Xmx)는 user_jvm_args.txt 와 bot_config 중 한 곳에서만 관리하도록 정리.
3. **봇 재시작 시 RCON 포트 재할당 문제.** 서버가 켜져 있으면 스캔 때 RCON 포트가 "사용 중"으로 보여 다른 포트를 고르고 server.properties 를 바꿈 → 켜져 있는 서버와 봇 설정이 어긋남 (재시작 전까지 RCON 안 됨). 1번 재연결과 같이 처리: 실행 중으로 확인된 서버는 RCON 포트를 건드리지 말 것. (RCON 비밀번호는 기존 값을 재사용하므로 문제 없음)

### 3단계 — 무인 운영
- 부팅 시 봇 자동 실행 (작업 스케줄러 또는 NSSM 서비스), 꺼지기 전에 켜져 있던 서버 자동 복구 (상태 파일)
- 주기적 `save-all` + 백업 (전원 차단 대비), 백업 무결성 확인 후 롤백
- 빈 서버 자동 종료(`ENABLE_AUTO_SHUTDOWN`)는 코드는 있으나 `is_server_running` 에 의존 → 2단계 후 검증

### 정리/선택
- Linux 전용 잔재 정리 여부 결정: `ScreenManager`, `/스크린정보`, `DEFAULT_TERMINAL_MODE` (Linux 서버로 갈 계획 없으면 Windows 백엔드로 대체)
- `ServerManager.servers_dir = base_path/'servers'` 는 mkdir 만 하고 안 쓰임 (SERVERS_DIR 와 별개) → 정리
- 공인 IP 변경 감지 / DuckDNS 갱신 (선택)

## 테스트

`python tests/run_all.py` — 각 테스트를 별도 프로세스로 실행 (settings.activate 는 프로세스당 1번).
- `test_permissions.py`: 조사, 부여/회수 규칙 전체, 저장·재로드, 저장 실패 롤백, 깨진 파일 격리, 명령어 경로·옵션 등급, 게이트(가짜 인터랙션)
- `test_integration.py`: 임시 폴더 + 임시 프로필(`profiles/itest.py`, 끝나면 삭제)로 봇 생성 → 스캔·포트 정책 → 명령어 등록 → 권한표 = 실제 명령어 → 권한 명령어 콜백. 게임 포트는 비어 있는 걸 골라 쓰므로 실제 서버가 켜진 PC 에서도 실행 가능.
- 디스코드에 실제 접속하는 테스트는 없다. 실제 동작 확인은 `run_dev.py` + 테스트 길드로.
- `screen` 이 없는 환경에서 ScreenManager 가 traceback 을 출력하지만 잡힌 예외라 무해함.

## 작업 규칙

- 코드 주석·로그·사용자 메시지는 한국어. 사용자에게 보이는 문장에서 등급 이름 뒤 조사는 `josa()` 사용.
- 기존 스타일 유지: 파일 맨 위 docstring 에 `경로:` 표기, `print` 로그 + 이모지.
- 이론적 개선보다 실제 배포에서 깨지는 것(타이밍, 자원 충돌, 네트워크, 전원 차단)을 우선.
- 숫자(포트·메모리 계산 등)는 다시 검증하고, 확실하지 않은 정보는 확실하지 않다고 명시하고, 빠뜨린 것은 빠뜨렸다고 말할 것.
- 커밋 전 `python tests/run_all.py` 통과. 새 기능/버그 수정에는 테스트 추가.
- **절대 커밋 금지**: `profiles/*.py`(example 제외), `data/`, `config.py`(구버전 설정), 토큰·비밀번호.
- 설정 파일은 템플릿(`profiles/example.py`) 방식 유지.
