"""
테스트용 가짜 봇: ProcessManager 로 서버를 띄운 뒤 그대로 대기 (테스트가 이 프로세스를 강제로 죽임)
경로: tests/fakes/fake_bot.py
사용: python fake_bot.py <레포> <서버폴더> <콘솔모드> <java> <인자...>
"""
import sys
import time
from pathlib import Path

repo, server_path, mode, *argv = sys.argv[1:]
sys.path.insert(0, repo)
from modules.minecraft.ProcessManager import ProcessManager  # noqa: E402

pm = ProcessManager(console_mode=mode)
ok, msg, t = pm.launch("fakebot", Path(server_path), argv, {"rcon_port": None})
print(f"launched {ok} {t.pid if t else msg}", flush=True)
while True:
    time.sleep(1)
