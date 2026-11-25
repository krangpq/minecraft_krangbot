"""
테스트용 가짜 마인크래프트 서버 (java 대신 실행)
경로: tests/fakes/fake_server.py

- 작업 폴더의 server.properties 를 읽어 게임 포트를 열고, RCON 이 켜져 있으면 RCON 서버도 엶
- RCON 명령: stop(종료), save-all [flush](저장 기록), list
- Ctrl+C(KeyboardInterrupt)를 받으면 "저장"하고 종료 (JVM 종료 훅 흉내)
- 동작은 .fake/events.txt 에 기록 → 테스트가 확인

옵션: --ignore-stop  --ignore-ctrl-c  --exit-now CODE  --stop-delay 초
"""
import argparse
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--ignore-stop", action="store_true")
ap.add_argument("--ignore-ctrl-c", action="store_true")
ap.add_argument("--exit-now", type=int, default=None)
ap.add_argument("--stop-delay", type=float, default=0.5)
opts = ap.parse_args()

cwd = Path.cwd()
(cwd / ".fake").mkdir(exist_ok=True)
(cwd / "logs").mkdir(exist_ok=True)
events = open(cwd / ".fake" / "events.txt", "a", encoding="utf-8")
log = open(cwd / "logs" / "latest.log", "w", encoding="utf-8")


def event(text):
    events.write(f"{text}\n")
    events.flush()


def logline(text):
    log.write(f"[fake] {text}\n")
    log.flush()
    print(text, flush=True)


props = {}
for line in (cwd / "server.properties").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        props[k.strip()] = v.strip()

event(f"start pid={os.getpid()}")
logline("Starting fake minecraft server")

if opts.exit_now is not None:
    logline("Error: fake crash on startup (예: 잘못된 Java 버전)")
    event("crash")
    sys.exit(opts.exit_now)

stop_event = threading.Event()

game = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
game.bind(("0.0.0.0", int(props.get("server-port", "25565"))))
game.listen(5)


def game_loop():
    while True:
        try:
            c, _ = game.accept()
            c.close()
        except OSError:
            return


threading.Thread(target=game_loop, daemon=True).start()


def recv_exact(c, n):
    data = b""
    while len(data) < n:
        chunk = c.recv(n - len(data))
        if not chunk:
            raise ConnectionError
        data += chunk
    return data


def send(c, req_id, ptype, body):
    payload = struct.pack("<ii", req_id, ptype) + body.encode("utf-8") + b"\x00\x00"
    c.sendall(struct.pack("<i", len(payload)) + payload)


def rcon_client(c):
    authed = False
    try:
        while True:
            (length,) = struct.unpack("<i", recv_exact(c, 4))
            data = recv_exact(c, length)
            req_id, ptype = struct.unpack("<ii", data[:8])
            body = data[8:-2].decode("utf-8")
            if ptype == 3:
                authed = body == props.get("rcon.password")
                send(c, req_id if authed else -1, 2, "")
                continue
            if not authed:
                send(c, -1, 2, "")
                continue
            event(f"rcon {body}")
            if body == "stop":
                if opts.ignore_stop:
                    send(c, req_id, 0, "Stopping (ignored)")
                else:
                    send(c, req_id, 0, "Stopping the server")
                    stop_event.set()
            elif body.startswith("save-all"):
                event("saved")
                send(c, req_id, 0, "Saved the game")
            elif body == "list":
                send(c, req_id, 0, "There are 0 of a max of 20 players online: ")
            else:
                send(c, req_id, 0, f"Unknown command: {body}")
    except (ConnectionError, OSError, struct.error):
        pass
    finally:
        c.close()


if props.get("enable-rcon") == "true":
    rcon = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rcon.bind(("127.0.0.1", int(props["rcon.port"])))
    rcon.listen(5)

    def rcon_loop():
        while True:
            try:
                c, _ = rcon.accept()
            except OSError:
                return
            threading.Thread(target=rcon_client, args=(c,), daemon=True).start()

    threading.Thread(target=rcon_loop, daemon=True).start()

logline('Done (1.0s)! For help, type "help"')
event("ready")

while True:
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
        time.sleep(opts.stop_delay)
        event("exit stop")
        sys.exit(0)
    except KeyboardInterrupt:
        event("ctrl-c")
        if opts.ignore_ctrl_c:
            continue
        event("saved")
        time.sleep(0.5)
        event("exit ctrl-c")
        sys.exit(0)
