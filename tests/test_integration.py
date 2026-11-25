"""
통합 테스트: 프로필 로드 → 봇 생성(스캔 포함) → 명령어 등록 → 권한표 점검 → 권한 명령어 콜백 → 포트 고정 확인
실행: python tests/test_integration.py   (또는 python tests/run_all.py)

- 임시 폴더에 가짜 서버 3개를 만들고, 임시 프로필(profiles/itest.py)로 봇을 생성합니다 (끝나면 삭제).
- 디스코드에는 접속하지 않습니다. 실제 서버 폴더·권한 파일은 건드리지 않습니다.
- 게임 포트는 지금 비어 있는 포트를 골라 쓰므로, 실제 마크 서버가 켜져 있는 PC에서도 돌릴 수 있습니다.
"""
import asyncio
import json
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

failures, count = [], 0


def check(cond, label):
    global count
    count += 1
    if not cond:
        failures.append(label)
        print("  FAIL:", label)


def props(folder):
    out = {}
    f = folder / "server.properties"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def free_game_port():
    """게임 포트 범위(25565-25600)에서 지금 비어 있는 포트 하나"""
    for port in range(25565, 25601):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    raise SystemExit("게임 포트 범위에 빈 포트가 없어 테스트를 못 돌려요")


GAME_PORT = free_game_port()
T = Path(tempfile.mkdtemp(prefix='krangbot-itest-'))
servers = T / "servers"
for name in ("alpha", "beta", "gamma"):
    (servers / name).mkdir(parents=True)
    (servers / name / "server.jar").write_bytes(b"dummy")
# alpha: GAME_PORT 고정 + 예전 RCON 기본값 25575 (게임 포트 범위)
(servers / "alpha" / "server.properties").write_text(f"server-port={GAME_PORT}\nenable-rcon=true\nrcon.port=25575\nrcon.password=keepme\n", encoding="utf-8")
(servers / "alpha" / "bot_config.json").write_text(json.dumps({"memory": {"min": 1024, "max": 2048}, "rcon": {"port": 25575, "auto_password": True}}), encoding="utf-8")
# beta: server.properties 없음 (새 서버)
# gamma: alpha 와 같은 포트
(servers / "gamma" / "server.properties").write_text(f"server-port={GAME_PORT}\n", encoding="utf-8")

profile = REPO / "profiles" / "itest.py"
profile.write_text(
    f"from pathlib import Path\nTOKEN='itest-token'\nBOT_OWNER_ID=1\n"
    f"SERVERS_DIR=Path(r'{servers}')\nBASE_PATH=Path(r'{T / 'base'}')\nDATA_DIR=Path(r'{T / 'data'}')\n",
    encoding="utf-8")

# alpha 가 "이미 켜져 있는" 상황: GAME_PORT 를 점유
busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
busy.bind(("0.0.0.0", GAME_PORT))
busy.listen(1)

try:
    import settings
    settings.activate("itest")
    check(settings.PROFILE == "itest" and settings.DATA_DIR == T / "data", "프로필 활성화")
    try:
        settings.activate("itest")
        check(False, "두 번 활성화 막혀야 함")
    except RuntimeError:
        check(True, "두 번 활성화 차단")

    import discord
    from discord import app_commands
    import bot as bot_module
    from modules.minecraft import setup_commands, setup_lifecycle_commands
    from modules.permissions import setup_permission_commands, audit_permission_table, Level

    print("\n===== 봇 생성 (스캔 로그) =====")
    b = bot_module.MinecraftBot()
    print("===== 스캔 끝 =====\n")

    cfg = b.mc.servers_config
    check(set(cfg) == {"alpha", "beta", "gamma"}, f"서버 3개 스캔: {sorted(cfg)}")

    print("[포트]")
    print(f"    테스트용 게임 포트: {GAME_PORT}")
    check(cfg["alpha"]["port"] == GAME_PORT and props(servers / "alpha")["server-port"] == str(GAME_PORT),
          "alpha: 사용 중이어도 포트 유지, server.properties 안 바뀜")
    check(cfg["gamma"]["port"] == GAME_PORT and props(servers / "gamma")["server-port"] == str(GAME_PORT),
          "gamma: 중복이어도 유지(경고만)")
    beta_port = cfg["beta"]["port"]
    check(25565 <= beta_port <= 25600 and beta_port != GAME_PORT
          and props(servers / "beta").get("server-port") == str(beta_port),
          f"beta: 새 서버 → 빈 게임 포트 할당·기록 (실제 {beta_port})")
    rcon_ports = [cfg[s]["rcon"]["port"] for s in ("alpha", "beta", "gamma")]
    print("    RCON:", dict(zip(("alpha", "beta", "gamma"), rcon_ports)))
    check(all(35575 <= p <= 35650 for p in rcon_ports), "RCON 전부 35575-35650")
    check(len(set(rcon_ports)) == 3, "RCON 포트 서로 다름")
    for s in ("alpha", "beta", "gamma"):
        check(props(servers / s).get("rcon.port") == str(cfg[s]["rcon"]["port"]), f"{s}: server.properties rcon.port 일치")
        bc = json.loads((servers / s / "bot_config.json").read_text(encoding="utf-8"))
        check(bc["rcon"]["port"] == cfg[s]["rcon"]["port"], f"{s}: bot_config.json rcon.port 반영")
    check(props(servers / "alpha").get("rcon.password") == "keepme", "alpha: 기존 RCON 비밀번호 유지")
    beta_pw = props(servers / "beta").get("rcon.password", "")
    check(beta_pw == cfg["beta"]["rcon"]["password"] and "server-port" not in beta_pw,
          f"beta: RCON 비밀번호에 다른 줄이 안 붙음 ({beta_pw!r})")
    print("    beta server.properties:", (servers / "beta" / "server.properties").read_text(encoding="utf-8").replace("\n", " | ")[:200])

    print("[명령어 등록 / 권한표]")
    setup_commands(b)
    setup_lifecycle_commands(b)
    setup_permission_commands(b)
    result = audit_permission_table(b.tree)
    check(result == {"unmapped": [], "missing": [], "bad_options": []}, f"권한표 = 실제 명령어: {result}")
    names = sorted(c.qualified_name for c in b.tree.walk_commands() if isinstance(c, app_commands.Command))
    print(f"    등록된 명령어 {len(names)}개:", ", ".join(names))
    check(not any(n in names for n in ("제어채널연결", "제어채널해제", "제어기능상태", "자동종료", "gcp상태확인")), "GCP 명령어 없음")
    check(isinstance(b.tree, bot_module.PermissionTree), "tree_cls = PermissionTree")

    print("[권한 명령어 콜백]")

    class Resp:
        def __init__(self): self.sent = []; self._done = False
        def is_done(self): return self._done
        async def send_message(self, content=None, *, ephemeral=False, embed=None):
            self.sent.append((content, ephemeral, embed)); self._done = True

    def inter(user):
        return SimpleNamespace(user=user, response=Resp(), client=b)

    owner = SimpleNamespace(id=1, display_name="소유자", name="owner", bot=False)
    friend = SimpleNamespace(id=500, display_name="친구", name="friend", bot=False)
    stranger = SimpleNamespace(id=600, display_name="모르는사람", name="x", bot=False)

    group = b.tree.get_command("권한")
    grant_cmd = group.get_command("부여")
    choice_param = next(p for p in grant_cmd.parameters if p.name == "등급")
    print("    등급 선택지:", [c.name for c in choice_param.choices])
    check([c.value for c in choice_param.choices] == [1, 2, 3], "선택지 = 멤버/운영자/관리자")

    async def run():
        it = inter(owner)
        await grant_cmd.callback(it, friend, app_commands.Choice(name="운영자", value=2))
        print("    /권한 부여:", it.response.sent[0][0])
        check(b.permissions.get_level(friend) == Level.OPERATOR and it.response.sent[0][1], "부여 콜백 → 운영자, ephemeral")

        it = inter(owner)
        await group.get_command("목록").callback(it)
        emb = it.response.sent[0][2]
        fields = {f.name: f.value for f in emb.fields}
        print("    /권한 목록:", fields)
        check("<@500>" in fields.get("운영자 (1명)", ""), "목록에 운영자 표시")

        my = b.tree.get_command("내권한")
        it = inter(friend); await my.callback(it)
        print("    /내권한(운영자):", it.response.sent[0][0].replace("\n", " / "))
        check("서버시작" in it.response.sent[0][0] and "명령어실행" not in it.response.sent[0][0], "운영자 사용 가능 목록")
        it = inter(stranger); await my.callback(it)
        print("    /내권한(미등록):", it.response.sent[0][0].replace("\n", " / "))
        check("등록돼 있지 않아요" in it.response.sent[0][0], "미등록 안내")

        it = inter(owner)
        await group.get_command("회수").callback(it, friend)
        print("    /권한 회수:", it.response.sent[0][0])
        check(b.permissions.get_level(friend) == Level.GUEST, "회수 콜백")
        await b.close()

    asyncio.run(run())
    check((T / "data" / "permissions.json").exists(), "권한 파일이 DATA_DIR 에 생성")
finally:
    busy.close()
    profile.unlink(missing_ok=True)

print(f"\n{count - len(failures)}/{count} 통과")
shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if failures else 0)
