"""
2단계 테스트: 시작 명령 결정(LaunchResolver) + 프로세스 실행·추적·재연결·중지(ProcessManager/ServerManager)
실행: python tests/test_process.py   (또는 python tests/run_all.py)

- 실제 서버팩 구조는 tests/fixtures/packs (C:\\mcserver 에서 실행 관련 파일만 복사한 것)를 임시 폴더로 복사해서 씀
- 실제 프로세스 테스트는 java 대신 tests/fakes/fake_server.py (파이썬 가짜 서버)
- Windows 에서는 가짜 서버가 최소화된 콘솔 창으로 잠깐씩 뜹니다 (작업 표시줄)
- 실제 서버 폴더(C:\\mcserver)와 켜져 있는 java 프로세스는 건드리지 않음
"""
import asyncio
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import psutil  # noqa: E402
import settings  # noqa: E402  (activate 안 함 — 기본값을 테스트에서 직접 바꿈)
from modules.minecraft import LaunchResolver as LR  # noqa: E402
from modules.minecraft.ProcessManager import ProcessManager  # noqa: E402
from modules.minecraft.ServerConfigurator import ServerConfigurator  # noqa: E402
from modules.minecraft.ServerScanner import ServerScanner  # noqa: E402
from modules.minecraft.ServerManager import ServerManager  # noqa: E402
from modules.minecraft.PortManager import PortManager  # noqa: E402

IS_WINDOWS = platform.system() == "Windows"
FIXTURES = REPO / "tests" / "fixtures" / "packs"
FAKE_SERVER = REPO / "tests" / "fakes" / "fake_server.py"
FAKE_BOT = REPO / "tests" / "fakes" / "fake_bot.py"
PY_NAMES = ("python.exe", "python", "python3") + ((os.path.basename(sys.executable).lower(),))

failures, count = [], 0


def check(cond, label):
    global count
    count += 1
    if not cond:
        failures.append(label)
        print("  FAIL:", label)
    else:
        print("  ok  :", label)


def free_port(start, end, exclude=()):
    for port in range(start, end + 1):
        if port in exclude:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    raise SystemExit(f"{start}-{end} 에 빈 포트가 없어요")


def events(folder):
    f = folder / ".fake" / "events.txt"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def wait_for(cond, timeout=10.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


T = Path(tempfile.mkdtemp(prefix="krangbot-ptest-"))
spawned = []  # 테스트가 끝나면 남은 가짜 서버 정리


# =====================================================================
print("\n[1] 시작 명령 결정 — 실제 서버팩 구조 복사본")
# =====================================================================
packs = T / "packs"
shutil.copytree(FIXTURES, packs)
# 서버팩 루트의 ServerStarterJar / installer 흉내 (실제 바이너리는 복사 안 함)
(packs / "forge_serverpack" / "server.jar").write_bytes(b"PK fake starter jar")
(packs / "forge_serverpack" / "forge-1.20.1-47.4.22-installer.jar").write_bytes(b"PK")

plan, why = LR.resolve_launch(packs / "forge_serverpack", {}, 1024, 4096)
check(plan and plan.kind == "forge", f"서버팩: Forge 로 인식 ({why})")
check(plan and plan.args == ["@user_jvm_args.txt",
                             "@libraries/net/minecraftforge/forge/1.20.1-47.4.22/win_args.txt" if IS_WINDOWS
                             else "@libraries/net/minecraftforge/forge/1.20.1-47.4.22/unix_args.txt", "nogui"]
      if IS_WINDOWS else plan is not None, f"서버팩: server.jar(ServerStarterJar) 대신 args 파일 사용 {plan.args if plan else None}")
check(plan and plan.mc_version == "1.20.1" and plan.loader_version == "47.4.22", "서버팩: MC 1.20.1 / Forge 47.4.22")
check(plan and (plan.memory_min_mb, plan.memory_max_mb) == (4096, 4096), f"서버팩: -Xmx4G -Xms4G → 4096/4096 ({plan.memory_min_mb if plan else None}/{plan.memory_max_mb if plan else None})")
check(plan and plan.jar_file is None and plan.memory_source == "user_jvm_args.txt", "서버팩: 메모리 출처 = user_jvm_args.txt")

plan, why = LR.resolve_launch(packs / "forge_plain", {}, 1024, 4096)
check(plan and plan.kind == "forge" and plan.loader_version == "47.4.23", f"루트 jar 없는 Forge 팩 인식 ({why})")
check(plan and plan.memory_max_mb == 12288 and plan.memory_min_mb is None, f"-Xmx12G → 12288MB ({plan.memory_max_mb if plan else None})")

plan, why = LR.resolve_launch(packs / "neoforge", {}, 1024, 4096)
check(plan and plan.kind == "neoforge", f"NeoForge 인식 ({why})")
check(plan and plan.mc_version == "1.21.1" and plan.loader_version == "21.1.248", f"NeoForge 21.1.248 → MC 1.21.1 ({plan.mc_version if plan else None})")
check(plan and (plan.memory_min_mb, plan.memory_max_mb) == (8192, 16384), "NeoForge: -Xms8G -Xmx16G → 8192/16384")

# Fabric (실제 withher 서버: start.bat 에 -Xms2G -Xmx16G, MC 26.3 → Java 25)
fab = packs / "fabric"
(fab / "fabric-server-launch.jar").write_bytes(b"PK")
(fab / ".fabric" / "server").mkdir(parents=True)
(fab / ".fabric" / "server" / "fabric-loader-server-0.20.1-minecraft-26.3.jar").write_bytes(b"PK")
(fab / ".fabric" / "server" / "26.3-server.jar").write_bytes(b"PK")
plan, why = LR.resolve_launch(fab, {}, 1024, 4096)
check(plan and plan.kind == "fabric" and plan.mc_version == "26.3" and plan.loader_version == "0.20.1",
      f"Fabric 인식: MC 26.3 / 로더 0.20.1 ({plan.describe() if plan else why})")
check(plan and plan.args == ["-Xms2048M", "-Xmx16384M", "-jar", "fabric-server-launch.jar", "nogui"]
      and plan.memory_source == "start.bat", f"Fabric: start.bat 의 -Xms2G -Xmx16G 사용 ({plan.args if plan else None})")
check(LR.required_java_major("26.3") == 25, "MC 26.3 → Java 25")
plan, _ = LR.resolve_launch(fab, {"memory": {"min": 1024, "max": 8192}}, 1024, 4096)
check(plan and plan.memory_max_mb == 8192 and plan.memory_source == "bot_config.json", "Fabric: bot_config memory 가 있으면 그게 우선")
shutil.rmtree(fab / ".fabric")
(fab / "versions" / "26.1").mkdir(parents=True)
plan, _ = LR.resolve_launch(fab, {}, 1024, 4096)
check(plan and plan.mc_version == "26.1", "Fabric: .fabric 이 없으면 versions/ 에서 MC 버전")

plan, _ = LR.resolve_launch(packs / "forge_plain", {"memory": {"min": 1024, "max": 4096}}, 1024, 4096)
check(plan and plan.memory_max_mb == 12288 and any("무시" in w for w in plan.warnings),
      "Forge 팩에 bot_config memory 가 있으면 무시하고 경고")

# run.bat 이 없는 파일을 가리키고 버전 폴더가 둘
multi = T / "multi"
shutil.copytree(packs / "forge_plain", multi)
args_name = LR.ARGS_FILE_NAME
newer = multi / "libraries/net/minecraftforge/forge/1.20.1-47.4.30"
newer.mkdir(parents=True)
(newer / args_name).write_text("-p x", encoding="utf-8")
(multi / LR.RUN_SCRIPT_NAME).write_text("java @user_jvm_args.txt @libraries/net/minecraftforge/forge/1.20.1-99.9.9/" + args_name + " %*\n", encoding="utf-8")
plan, _ = LR.resolve_launch(multi, {}, 1024, 4096)
check(plan and plan.loader_version == "47.4.30" and len(plan.warnings) >= 2,
      f"run.bat 경로가 없으면 libraries 에서 가장 높은 버전 + 경고 ({plan.loader_version if plan else None})")

jar_dir = T / "jar_only"
jar_dir.mkdir()
(jar_dir / "paper-1.20.4.jar").write_bytes(b"PK")
(jar_dir / "forge-1.20.1-installer.jar").write_bytes(b"PK")
plan, _ = LR.resolve_launch(jar_dir, {"memory": {"min": 2048, "max": 6144}}, 1024, 4096)
check(plan and plan.kind == "jar" and plan.jar_file == "paper-1.20.4.jar"
      and plan.args == ["-Xms2048M", "-Xmx6144M", "-jar", "paper-1.20.4.jar", "nogui"],
      f"일반 jar: installer 제외 + bot_config 메모리 ({plan.args if plan else None})")
(jar_dir / "server.jar").write_bytes(b"PK")
plan, _ = LR.resolve_launch(jar_dir, {}, 1024, 4096)
check(plan and plan.jar_file == "server.jar" and plan.memory_max_mb == 4096, "일반 jar: server.jar 우선, 기본 메모리")

plan, _ = LR.resolve_launch(jar_dir, {"launch": {"args": ["-Xmx3G", "-jar", "custom.jar"]}}, 1024, 4096)
check(plan and plan.kind == "custom" and plan.memory_max_mb == 3072, "bot_config launch.args 가 최우선")
plan, why = LR.resolve_launch(jar_dir, {"launch": {"args": "java -jar x"}}, 1024, 4096)
check(plan is None, f"launch.args 형식 오류 거부 ({why})")

empty = T / "empty"
empty.mkdir()
plan, why = LR.resolve_launch(empty, {}, 1024, 4096)
check(plan is None, f"실행할 게 없으면 None ({why})")

check(LR.parse_memory_args(["-Xmx512M", "-Xms1g"]) == (1024, 512), "메모리 단위 M/g")
check(LR.parse_memory_args(["-Xmx2048m", "-Xmx4G"]) == (None, 4096), "-Xmx 여러 번이면 마지막")
check(LR.parse_memory_args(["-Xmx1073741824"]) == (None, 1024), "단위 없음 = 바이트")
check(LR.parse_memory_args(["-XX:+UseG1GC", "-Xss1M"]) == (None, None), "-Xss 등은 무시")

for mc, want in (("1.12.2", 8), ("1.16.5", 8), ("1.17.1", 16), ("1.18.2", 17), ("1.20.1", 17),
                 ("1.20.4", 17), ("1.20.5", 21), ("1.21.1", 21), (None, None)):
    check(LR.required_java_major(mc) == want, f"MC {mc} → Java {want}")

installed = {17: "j17", 21: "j21", 25: "j25"}
check(LR.select_java(17, installed=installed)[0] == "j17", "1.20.1(17 필요) → 17 (가장 가까운 버전)")
check(LR.select_java(21, installed=installed)[0] == "j21", "1.21.1(21 필요) → 21")
check(LR.select_java(22, installed=installed)[0] == "j25", "22 필요 → 25")
check(LR.select_java(17, explicit="mine", installed=installed)[0] == "mine", "bot_config java 가 최우선")
check(LR.select_java(17, java_paths={"21": "p21"}, installed=installed)[0] == "p21", "JAVA_PATHS 가 자동 감지보다 우선 (문자열 키도 허용)")
check(LR.select_java(17, installed={}, default_java="nojava-xyz")[0] == "nojava-xyz", "못 찾으면 DEFAULT_JAVA")
check(LR.select_java(None, installed=installed, default_java="nojava-xyz")[1].startswith("MC 버전을 몰라서"), "버전 모르면 기본값")
detected = LR.detect_installed_javas(refresh=True)
print(f"    (참고) 이 PC 에서 감지된 Java: {detected}")


# =====================================================================
print("\n[2] 스캐너 — 서버팩 복사본 (실행 중 아님)")
# =====================================================================
scan_dir = T / "scan"
scan_dir.mkdir()
for name in ("forge_serverpack", "forge_plain", "neoforge"):
    shutil.copytree(packs / name, scan_dir / name)
conf = ServerConfigurator(1024, 4096)
pm_scan = ProcessManager(adopt_names=PY_NAMES)
scanned = ServerScanner(scan_dir, conf, process_manager=pm_scan).scan_all_servers()
check(set(scanned) == {"forge_serverpack", "forge_plain", "neoforge"}, f"루트 jar 없는 팩도 전부 등록 ({sorted(scanned)})")
for sid, c in scanned.items():
    props = ServerConfigurator.read_properties(scan_dir / sid)
    bc = json.loads((scan_dir / sid / "bot_config.json").read_text(encoding="utf-8"))
    check(props.get("server-port") == "25565", f"{sid}: 게임 포트 25565 그대로")
    check(props.get("enable-rcon") == "true" and 35575 <= int(props["rcon.port"]) <= 35650, f"{sid}: RCON 켜짐, 35575-35650 ({props.get('rcon.port')})")
    check("memory" not in bc, f"{sid}: Forge/NeoForge 팩은 bot_config 에 memory 안 넣음")
    check(c["start_command"].startswith("java @user_jvm_args.txt @libraries/"), f"{sid}: 표시용 명령 {c['start_command'][:60]}…")
check(scanned["neoforge"]["memory"]["max"] == 16384, "스캔 결과 메모리 = user_jvm_args.txt")

fscan = T / "scan_fabric"
fscan.mkdir()
shutil.copytree(fab, fscan / "fabric")
fscanned = ServerScanner(fscan, ServerConfigurator(1024, 4096), process_manager=pm_scan).scan_all_servers()
fbc = json.loads((fscan / "fabric" / "bot_config.json").read_text(encoding="utf-8"))
check(fscanned.get("fabric", {}).get("launch_kind") == "fabric" and fbc.get("memory") == {"min": 2048, "max": 16384},
      f"Fabric 스캔: start.bat 메모리를 bot_config.json 으로 옮겨 적음 ({fbc.get('memory')})")
fscanned = ServerScanner(fscan, ServerConfigurator(1024, 4096), process_manager=pm_scan).scan_all_servers()
check(fscanned["fabric"]["memory"]["source"] == "bot_config.json", "Fabric 재스캔: 이후엔 bot_config.json 이 기준")


# =====================================================================
print("\n[3] 실제 프로세스 — 가짜 서버")
# =====================================================================
settings.START_CHECK_SECONDS = 2
settings.STOP_TIMEOUT = 8
settings.FORCE_STOP_GRACE = 4
settings.AUTO_FORCE_KILL_ON_TIMEOUT = False
settings.STOP_SERVERS_ON_BOT_EXIT = False
settings.MEMORY_CHECK_ENABLED = True
settings.SERVER_CONSOLE_MODE = "minimized"

servers = T / "servers"
servers.mkdir()
GAME1 = free_port(25565, 25600)
GAME2 = free_port(25565, 25600, exclude={GAME1})
RCON1 = free_port(35575, 35650)
RCON2 = free_port(35575, 35650, exclude={RCON1})


def make_fake(name, game, rcon, extra_args=(), rcon_enabled=True, password="pw-test"):
    d = servers / name
    d.mkdir()
    lines = [f"server-port={game}"]
    if rcon_enabled:
        lines += ["enable-rcon=true", f"rcon.port={rcon}", f"rcon.password={password}"]
    else:
        lines += ["enable-rcon=false"]
    (d / "server.properties").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (d / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    bc = {"name": name, "java": sys.executable,
          "launch": {"args": ["-I", str(FAKE_SERVER), *extra_args]},
          "rcon": {"port": rcon, "auto_password": True}}
    (d / "bot_config.json").write_text(json.dumps(bc), encoding="utf-8")
    return d


f1 = make_fake("fake1", GAME1, RCON1)
f2 = make_fake("fake2", GAME1, RCON2)  # fake1 과 같은 게임 포트


def build_manager():
    pm = ProcessManager(console_mode=settings.SERVER_CONSOLE_MODE, adopt_names=PY_NAMES)
    cfgs = ServerScanner(servers, ServerConfigurator(1024, 4096), process_manager=pm).scan_all_servers()
    for c in cfgs.values():
        c["terminal_mode"] = "process"
    return ServerManager(SimpleNamespace(), str(T / "base"), cfgs, "fake1", process_manager=pm), pm


async def main():
    mgr, pm = build_manager()

    ok, msg = await mgr.start_server("fake1")
    print("    시작:", msg.replace("\n", " / "))
    check(ok, "fake1 시작")
    state = json.loads((f1 / ".krangbot" / "process.json").read_text(encoding="utf-8"))
    check(state["pid"] == mgr.running_servers["fake1"].pid and state["rcon_port"] == RCON1
          and state["game_port"] == GAME1 and state["cmdline"] and state["create_time"] > 0,
          f"PID 파일 기록 (pid={state['pid']}, rcon={state['rcon_port']})")
    check(mgr.is_process_running("fake1"), "is_process_running = True")
    check(wait_for(lambda: mgr.is_server_running("fake1"), 10), "게임 포트 열림 → is_server_running = True")
    check(not PortManager.is_port_open(GAME1), "PortManager.is_port_open: 사용 중 포트를 '사용 중'으로 판단")
    ok, msg = await mgr.start_server("fake1")
    check(not ok and "이미 실행 중" in msg, "중복 시작 거부")
    ok, msg = await mgr.start_server("fake2")
    check(not ok and "동시에 켤 수 없습니다" in msg, f"같은 게임 포트 서버 동시 시작 거부 ({msg.splitlines()[0]})")

    ok, msg = await mgr.send_command("fake1", "list")
    check(ok and "players online" in msg, "RCON 명령 (list)")

    # ── 봇 재시작 흉내: 새 매니저로 다시 스캔 → 재연결, RCON 포트·파일 유지
    props_before = (f1 / "server.properties").read_bytes()
    bc_before = (f1 / "bot_config.json").read_bytes()
    mgr2, pm2 = build_manager()
    check(mgr2.is_process_running("fake1") and not mgr2.is_external("fake1"), "봇 재시작 후 PID 파일로 재연결")
    check(mgr2.servers_config["fake1"]["rcon"]["port"] == RCON1, "실행 중 서버의 RCON 포트 유지")
    check((f1 / "server.properties").read_bytes() == props_before and (f1 / "bot_config.json").read_bytes() == bc_before,
          "실행 중 서버의 server.properties / bot_config.json 안 바뀜")
    ok, msg = await mgr2.send_command("fake1", "list")
    check(ok, "재연결 후 RCON 동작")

    # 강제로 RCON 포트를 차지한 상태에서 재스캔해도 유지 (예전 버그: '사용 중'이라 다른 포트로 옮김)
    check(not PortManager.is_port_open(RCON1), "RCON 포트가 사용 중인 상태 (재할당 버그 재현 조건)")

    ok, msg = await mgr2.stop_server("fake1")
    print("    중지:", msg)
    check(ok and "RCON stop" in msg, "정상 중지 (RCON stop)")
    check("exit stop" in events(f1), "가짜 서버가 stop 으로 종료")
    check(not (f1 / ".krangbot" / "process.json").exists(), "중지 후 PID 파일 삭제")
    check(not mgr2.is_process_running("fake1"), "중지 후 is_process_running = False")

    # ── 봇이 시작 직후 죽는 서버
    f3 = make_fake("crash", free_port(25565, 25600, exclude={GAME1, GAME2}), free_port(35575, 35650, exclude={RCON1, RCON2}),
                   extra_args=["--exit-now", "1"])
    mgr3, _ = build_manager()
    ok, msg = await mgr3.start_server("crash")
    check(not ok and "시작 직후 종료" in msg and "fake crash" in msg, "바로 죽는 서버 → 실패 + latest.log 끝부분")
    check(not (f3 / ".krangbot" / "process.json").exists(), "실패하면 PID 파일 정리")
    shutil.rmtree(f3)

    # ── stop 을 무시하는 서버: 시간 초과 → 자동 강제 종료 안 함 → 강제 중지(Ctrl+C)
    shutil.rmtree(f1)
    f1b = make_fake("fake1", GAME1, RCON1, extra_args=["--ignore-stop"])
    mgr4, _ = build_manager()
    ok, _ = await mgr4.start_server("fake1")
    check(ok, "stop 무시하는 서버 시작")
    t0 = time.time()
    ok, msg = await mgr4.stop_server("fake1")
    check(not ok and "아직 꺼지지 않았습니다" in msg and time.time() - t0 >= settings.STOP_TIMEOUT - 1,
          f"STOP_TIMEOUT({settings.STOP_TIMEOUT}초) 후에도 안 꺼지면 알리기만 함")
    check(mgr4.is_process_running("fake1"), "자동 강제 종료 안 됨 (AUTO_FORCE_KILL_ON_TIMEOUT=False)")
    if IS_WINDOWS:
        ok, msg = await mgr4.stop_server("fake1", force=True)
        print("    강제:", msg)
        ev = events(f1b)
        check(ok and "Ctrl+C" in msg, "강제 중지 → Ctrl+C 로 종료")
        check("rcon save-all flush" in ev and "exit ctrl-c" in ev, f"강제 중지: save-all flush → Ctrl+C 저장 후 종료 ({ev[-4:]})")
    else:
        await mgr4.stop_server("fake1", force=True)

    # ── Ctrl+C 까지 무시하는 서버 → 프로세스 강제 종료
    shutil.rmtree(f1b)
    f1c = make_fake("fake1", GAME1, RCON1, extra_args=["--ignore-stop", "--ignore-ctrl-c"])
    mgr5, _ = build_manager()
    await mgr5.start_server("fake1")
    pid = mgr5.running_servers["fake1"].pid
    ok, msg = await mgr5.stop_server("fake1", force=True)
    check(ok and "강제 종료" in msg and not psutil.pid_exists(pid), "Ctrl+C 도 안 먹으면 FORCE_STOP_GRACE 후 프로세스 강제 종료")
    check(not (f1c / ".krangbot" / "process.json").exists(), "강제 종료 후 PID 파일 삭제")

    # ── RCON 이 안 되는 서버(비밀번호 틀림) → 정상 중지가 Ctrl+C 로 대체
    shutil.rmtree(f1c)
    f1d = make_fake("fake1", GAME1, RCON1)
    mgr6, _ = build_manager()
    mgr6.rcon_clients["fake1"].password = "wrong"
    await mgr6.start_server("fake1")
    ok, msg = await mgr6.stop_server("fake1")
    if IS_WINDOWS:
        check(ok and "Ctrl+C" in msg and "exit ctrl-c" in events(f1d), f"RCON 실패 → Ctrl+C 로 정상 중지 ({msg})")
    else:
        check(ok, "RCON 실패 → SIGINT 로 정상 중지")

    # ── 봇 프로세스가 죽어도 서버는 살아 있음 + 새 봇이 재연결
    for mode in (("minimized", "hidden") if IS_WINDOWS else ("log",)):
        shutil.rmtree(servers / "fake1")
        fb = make_fake("fake1", GAME1, RCON1)
        flags = subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0
        bot_proc = subprocess.Popen([sys.executable, "-I", str(FAKE_BOT), str(REPO), str(fb), mode,
                                     sys.executable, "-I", str(FAKE_SERVER)],
                                    creationflags=flags, stdout=subprocess.PIPE, text=True)
        spawned.append(bot_proc.pid)
        line = bot_proc.stdout.readline().strip()
        check(line.startswith("launched True"), f"[{mode}] 가짜 봇이 서버 실행 ({line})")
        server_pid = int(line.split()[-1]) if line.startswith("launched True") else -1
        spawned.append(server_pid)
        wait_for(lambda: "ready" in events(fb), 10)
        psutil.Process(bot_proc.pid).kill()  # 봇이 갑자기 죽음 (작업 관리자 강제 종료와 같음)
        bot_proc.wait(10)
        time.sleep(1)
        check(psutil.pid_exists(server_pid) and psutil.Process(server_pid).is_running(), f"[{mode}] 봇이 죽어도 서버 생존")
        mgr7, _ = build_manager()
        check(mgr7.is_process_running("fake1") and mgr7.running_servers["fake1"].pid == server_pid,
              f"[{mode}] 새 봇이 PID 파일로 재연결")
        if IS_WINDOWS:
            ok = await asyncio.to_thread(mgr7.pm.send_ctrl_c, "fake1")
            check(ok and wait_for(lambda: not psutil.pid_exists(server_pid), 10) and "exit ctrl-c" in events(fb),
                  f"[{mode}] 콘솔에 Ctrl+C 전달 → 저장 후 종료")
        ok, _ = await mgr7.stop_server("fake1")

    # ── 봇 밖에서 켠 서버 (run.bat 직접 실행 흉내)
    shutil.rmtree(servers / "fake1")
    fe = make_fake("fake1", GAME1, RCON1)
    ext = subprocess.Popen([sys.executable, "-I", str(FAKE_SERVER)], cwd=str(fe),
                           creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0)
    spawned.append(ext.pid)
    wait_for(lambda: "ready" in events(fe), 10)
    mgr8, _ = build_manager()
    check(mgr8.is_process_running("fake1") and mgr8.is_external("fake1"), "봇 밖에서 켠 서버를 작업 폴더로 찾아 '외부 실행' 등록")
    ok, msg = await mgr8.start_server("fake1")
    check(not ok and "이미 실행 중" in msg, "외부 실행 중인 서버 중복 시작 거부")
    ok, msg = await mgr8.stop_server("fake1")
    if not ok:
        print("    [진단] events:", events(fe), "poll:", ext.poll(), "props:", ServerConfigurator.read_properties(fe),
              "rcon cfg:", mgr8.servers_config["fake1"]["rcon"], "tracked pid:",
              getattr(mgr8.running_servers.get("fake1"), "pid", None), "ext pid:", ext.pid)
    check(ok and ext.wait(10) == 0, f"외부 실행 서버도 RCON 으로 중지 ({msg})")

    # ── PID 재사용 방지
    pmx = ProcessManager(adopt_names=PY_NAMES)
    me = psutil.Process()
    fake_rec = {"pid": me.pid, "create_time": me.create_time() - 1000, "exe": me.exe(), "cmdline": me.cmdline()}
    proc, why = pmx.verify_record(fake_rec)
    check(proc is None and "재사용" in why, f"생성 시각이 다르면 다른 프로세스로 판단 ({why})")
    fake_rec = {"pid": me.pid, "create_time": me.create_time(), "exe": me.exe(), "cmdline": ["java", "-jar", "x.jar"]}
    proc, why = pmx.verify_record(fake_rec)
    check(proc is None and "명령줄" in why, f"명령줄이 다르면 거부 ({why})")
    fake_rec = {"pid": me.pid, "create_time": me.create_time(), "exe": me.exe(), "cmdline": me.cmdline()}
    proc, why = pmx.verify_record(fake_rec, server_path=T / "elsewhere")
    check(proc is None and "작업 폴더" in why, f"작업 폴더가 다르면 거부 ({why})")
    stale_dir = servers / "stale"
    (stale_dir / ".krangbot").mkdir(parents=True)
    (stale_dir / ".krangbot" / "process.json").write_text(json.dumps(
        {"pid": me.pid, "create_time": 1.0, "exe": me.exe(), "cmdline": me.cmdline()}), encoding="utf-8")
    check(pmx.find_running("stale", stale_dir, adopt_external=False) is None
          and (stale_dir / ".krangbot" / "process.json.stale").exists(), "무효 PID 파일은 .stale 로 옮기고 무시")
    (stale_dir / ".krangbot" / "process.json").write_text("{깨짐", encoding="utf-8")
    check(pmx.find_running("stale", stale_dir, adopt_external=False) is None
          and (stale_dir / ".krangbot" / "process.json.corrupt").exists(), "깨진 PID 파일은 .corrupt 로 옮기고 무시")
    shutil.rmtree(stale_dir)

    # ── 메모리 검사
    big = make_fake("big", free_port(25565, 25600, exclude={GAME1, GAME2}), free_port(35575, 35650, exclude={RCON1, RCON2}),
                    extra_args=["-Xmx99999G"])
    mgr9, _ = build_manager()
    ok, msg = await mgr9.start_server("big")
    check(not ok and "메모리 부족" in msg, "가용 RAM 보다 큰 -Xmx 면 시작 거부")
    check(not (big / ".krangbot" / "process.json").exists(), "메모리 부족 거부 시 프로세스 안 띄움")
    shutil.rmtree(big)

    # ── 봇 종료 시 서버 유지 (기본값)
    shutil.rmtree(servers / "fake1")
    make_fake("fake1", GAME1, RCON1)
    mgr10, _ = build_manager()
    await mgr10.start_server("fake1")
    pid = mgr10.running_servers["fake1"].pid
    await mgr10.cleanup_on_shutdown()
    check(psutil.pid_exists(pid), "STOP_SERVERS_ON_BOT_EXIT=False → 봇 종료 정리에서 서버 안 끔")
    settings.STOP_SERVERS_ON_BOT_EXIT = True
    await mgr10.cleanup_on_shutdown()
    check(wait_for(lambda: not psutil.pid_exists(pid), 10), "STOP_SERVERS_ON_BOT_EXIT=True → 같이 끔")
    settings.STOP_SERVERS_ON_BOT_EXIT = False


try:
    asyncio.run(main())
except Exception:
    import traceback
    traceback.print_exc()
    failures.append("예외 발생")
finally:
    # 남은 가짜 서버 정리 (테스트 폴더에서 실행된 python 만)
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() in PY_NAMES and str(T).lower() in (p.cwd() or "").lower():
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    for pid in spawned:
        try:
            psutil.Process(pid).kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            pass

print(f"\n{count - len(failures)}/{count} 통과")
time.sleep(0.5)
shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if failures else 0)
