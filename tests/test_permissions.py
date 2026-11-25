"""
권한 매니저 / 권한표 / 게이트 테스트
실행: python tests/test_permissions.py   (또는 python tests/run_all.py)
디스코드 연결 없이 가짜 인터랙션으로 검사합니다.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import discord
from discord import app_commands

from modules.permissions.PermissionTable import (
    Level, josa, requirement, resolve_command_path, COMMAND_LEVELS,
)
from modules.permissions.PermissionManager import PermissionManager
from modules.permissions.PermissionTree import PermissionTree, InsufficientLevel

failures = []
count = 0


def check(cond, label):
    global count
    count += 1
    if not cond:
        failures.append(label)
        print("  FAIL:", label)


def U(uid, name=None, bot=False):
    return SimpleNamespace(id=uid, display_name=name or f"user{uid}", name=name or f"user{uid}", bot=bot)


OWNER, A, B, C, D, BOT = U(1, "owner"), U(2, "알파"), U(3, "브라보"), U(4, "찰리"), U(5, "델타"), U(99, "봇", bot=True)

# ------------------------------------------------------------------
print("[1] 조사")
check(josa("관리자", "이라", "라") == "관리자라", "관리자라")
check(josa("미등록", "이라", "라") == "미등록이라", "미등록이라")
check(josa("멤버", "이에요", "예요") == "멤버예요", "멤버예요")
check(josa("미등록", "이에요", "예요") == "미등록이에요", "미등록이에요")
check(josa("운영자", "으로", "로") == "운영자로", "운영자로")
check(josa("소유자 전용", "으로", "로") == "소유자 전용으로", "전용으로")
check(josa("서울", "으로", "로") == "서울로", "ㄹ받침 로")

# ------------------------------------------------------------------
print("[2] 부여/회수 규칙")
tmp = Path(tempfile.mkdtemp(prefix='krangbot-test-'))
f = tmp / "data" / "permissions.json"
pm = PermissionManager(f, owner_id=OWNER.id)
check(pm.get_level(OWNER) == Level.OWNER, "소유자 = OWNER")
check(pm.get_level(A) == Level.GUEST, "미등록 = GUEST")

ok, msg = pm.grant(A, B, Level.MEMBER); check(not ok, f"GUEST는 부여 불가: {msg}")
ok, msg = pm.grant(OWNER, A, Level.ADMIN); check(ok and pm.get_level(A) == Level.ADMIN, f"소유자→관리자 부여: {msg}")
print("   ", msg)
ok, msg = pm.grant(A, B, Level.OPERATOR); check(ok and pm.get_level(B) == Level.OPERATOR, f"관리자→운영자 부여: {msg}")
ok, msg = pm.grant(A, C, Level.ADMIN); check(not ok and pm.get_level(C) == Level.GUEST, f"관리자→관리자 부여 불가: {msg}")
print("   ", msg)
ok, msg = pm.grant(A, A, Level.MEMBER); check(not ok, f"자기 자신 불가: {msg}")
ok, msg = pm.grant(A, OWNER, Level.MEMBER); check(not ok, f"소유자 대상 불가: {msg}")
ok, msg = pm.grant(OWNER, BOT, Level.MEMBER); check(not ok, f"봇 대상 불가: {msg}")
ok, msg = pm.grant(OWNER, C, Level.OWNER); check(not ok, f"OWNER 부여 불가: {msg}")
ok, msg = pm.grant(OWNER, C, Level.GUEST); check(not ok, f"GUEST 부여 불가(회수 써야): {msg}")
ok, msg = pm.grant(B, D, Level.MEMBER); check(not ok and pm.get_level(D) == Level.GUEST, f"운영자는 권한표상 부여 불가: {msg}")
print("   ", msg)
ok, msg = pm.grant(OWNER, C, Level.ADMIN); check(ok, "소유자→C 관리자")
ok, msg = pm.grant(A, C, Level.MEMBER); check(not ok and pm.get_level(C) == Level.ADMIN, f"관리자가 다른 관리자 강등 불가: {msg}")
print("   ", msg)
ok, msg = pm.grant(A, B, Level.OPERATOR); check(ok and "이미" in msg, f"같은 등급 재부여: {msg}")
print("   ", msg)
ok, msg = pm.grant(A, B, Level.MEMBER); check(ok and pm.get_level(B) == Level.MEMBER, f"운영자→멤버 강등: {msg}")
print("   ", msg)

ok, msg = pm.revoke(B, A); check(not ok, f"멤버는 회수 불가: {msg}")
ok, msg = pm.revoke(A, C); check(not ok, f"관리자가 관리자 회수 불가: {msg}")
ok, msg = pm.revoke(A, OWNER); check(not ok, f"소유자 회수 불가: {msg}")
ok, msg = pm.revoke(A, D); check(not ok, f"미등록 회수 불가: {msg}")
ok, msg = pm.revoke(A, A); check(not ok, f"자기 회수 불가: {msg}")
ok, msg = pm.revoke(A, B); check(ok and pm.get_level(B) == Level.GUEST, f"관리자→멤버 회수: {msg}")
print("   ", msg)

# ------------------------------------------------------------------
print("[3] 저장/재로드")
pm.grant(A, B, Level.OPERATOR)
pm2 = PermissionManager(f, owner_id=OWNER.id)
check(pm2.get_level(A) == Level.ADMIN and pm2.get_level(B) == Level.OPERATOR and pm2.get_level(C) == Level.ADMIN,
      "재로드 후 등급 유지")
data = json.loads(f.read_text(encoding="utf-8"))
check(data["version"] == 1 and set(data["users"]) == {"2", "3", "4"}, f"파일 구조: {data}")
check(not list(f.parent.glob("*.tmp")), "임시 파일 안 남음")
check([e[0] for e in pm2.list_entries()][:2] == [2, 4] or [e[0] for e in pm2.list_entries()][:2] == [4, 2],
      "목록 정렬: 관리자 먼저")
check(pm2.list_entries()[-1][0] == 3, "목록 정렬: 운영자 마지막")

print("[4] 저장 실패 시 롤백")
orig = PermissionManager._replace_with_retry
def boom(*a, **k): raise PermissionError("locked")
PermissionManager._replace_with_retry = staticmethod(boom)
ok, msg = pm2.grant(A, D, Level.MEMBER)
check(not ok and pm2.get_level(D) == Level.GUEST, f"부여 저장 실패 → 롤백: {msg}")
ok, msg = pm2.revoke(A, B)
check(not ok and pm2.get_level(B) == Level.OPERATOR, f"회수 저장 실패 → 롤백: {msg}")
check(not list(f.parent.glob("*.tmp")), "실패해도 임시 파일 정리")
PermissionManager._replace_with_retry = orig
pm3 = PermissionManager(f, owner_id=OWNER.id)
check(pm3.get_level(D) == Level.GUEST and pm3.get_level(B) == Level.OPERATOR, "디스크도 변경 전 상태")

print("[5] 깨진 파일 / 이상한 항목")
f.write_text("{ 이건 json 아님", encoding="utf-8")
pm4 = PermissionManager(f, owner_id=OWNER.id)
check(pm4.get_level(A) == Level.GUEST and pm4.get_level(OWNER) == Level.OWNER, "깨진 파일 → 빈 목록, 소유자만")
check(not f.exists() and len(list(f.parent.glob("permissions.corrupt-*.json"))) == 1, "깨진 파일 격리")
f.write_text(json.dumps({"version": 1, "users": {
    "2": {"level": 3, "name": "ok"}, "3": {"level": 4, "name": "가짜소유자"},
    "4": {"level": 9}, "x": {"level": 1}, "5": {"name": "level없음"}, "1": {"level": 1}}}), encoding="utf-8")
pm5 = PermissionManager(f, owner_id=OWNER.id)
check(pm5.get_level(A) == Level.ADMIN, "정상 항목 로드")
check(pm5.get_level(B) == Level.GUEST, "파일에 넣은 OWNER(4) 무시")
check(pm5.get_level(C) == Level.GUEST and pm5.get_level(D) == Level.GUEST, "이상한 항목 무시")
check(pm5.get_level(OWNER) == Level.OWNER, "소유자 항목이 파일에 있어도 OWNER")

# ------------------------------------------------------------------
print("[6] 명령어 경로 / 옵션 등급")
name, opts = resolve_command_path({"name": "서버시작", "type": 1, "options": [{"name": "서버", "type": 3, "value": "jujutsu"}]})
check(name == "서버시작" and opts[0]["value"] == "jujutsu", "단일 명령어")
name, opts = resolve_command_path({"name": "권한", "type": 1, "options": [
    {"name": "부여", "type": 1, "options": [{"name": "대상", "type": 6, "value": "3"}, {"name": "등급", "type": 4, "value": 2}]}]})
check(name == "권한 부여" and len(opts) == 2, f"그룹 하위 명령어: {name}")
check(requirement("서버중지", [{"name": "강제", "value": False}]) == (Level.OPERATOR, None), "강제 False → 운영자")
check(requirement("서버중지", [{"name": "강제", "value": True}]) == (Level.ADMIN, "강제"), "강제 True → 관리자")
check(requirement("서버중지", []) == (Level.OPERATOR, None), "옵션 없음 → 운영자")
check(requirement("없는명령어", [])[0] == Level.OWNER, "표에 없는 명령어 → 소유자")


# ------------------------------------------------------------------
print("[7] 게이트(interaction_check / on_error)")


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.autocompleted = None
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, *, ephemeral=False, embed=None):
        self.sent.append((content, ephemeral, embed))
        self._done = True

    async def autocomplete(self, choices):
        self.autocompleted = choices
        self._done = True


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, *, ephemeral=False, embed=None):
        self.sent.append((content, ephemeral))


def interaction(user, data, client, itype=discord.InteractionType.application_command):
    return SimpleNamespace(type=itype, data=data, user=user, client=client,
                           response=FakeResponse(), followup=FakeFollowup())


async def run_gate_tests():
    client = discord.Client(intents=discord.Intents.default())
    tree = PermissionTree(client)
    client.permissions = pm2  # A=관리자, B=운영자, C=관리자, OWNER

    start = {"name": "서버시작", "type": 1, "options": []}
    stop_force = {"name": "서버중지", "type": 1, "options": [{"name": "강제", "type": 5, "value": True}]}
    myperm = {"name": "내권한", "type": 1}

    check(await tree.interaction_check(interaction(B, start, client)) is True, "운영자 → 서버시작 허용")
    check(await tree.interaction_check(interaction(D, myperm, client)) is True, "미등록 → 내권한 허용")

    it = interaction(D, start, client)
    try:
        await tree.interaction_check(it)
        check(False, "미등록 → 서버시작 막혀야 함")
    except InsufficientLevel as e:
        check(e.required == Level.OPERATOR and e.current == Level.GUEST, "미등록 → 서버시작 InsufficientLevel")
        await tree.on_error(it, e)
        content, eph, _ = it.response.sent[0]
        check(eph and "운영자" in content and "화이트리스트" in content, f"안내 메시지: {content!r}")
        print("    미등록 안내:", content.replace("\n", " / "))

    it = interaction(B, stop_force, client)
    try:
        await tree.interaction_check(it)
        check(False, "운영자 → 강제중지 막혀야 함")
    except InsufficientLevel as e:
        check(e.option == "강제" and e.required == Level.ADMIN, "옵션 때문에 막힘")
        it.response._done = True  # 이미 응답한 상태 → followup 으로 가야 함
        await tree.on_error(it, SimpleNamespace(original=e))  # CommandInvokeError 처럼 감싸진 경우
        check(it.followup.sent and "강제" in it.followup.sent[0][0], f"followup 안내: {it.followup.sent}")
        print("    옵션 안내:", it.followup.sent[0][0].replace("\n", " / "))
    check(await tree.interaction_check(interaction(A, stop_force, client)) is True, "관리자 → 강제중지 허용")

    it = interaction(D, {"name": "서버시작", "type": 1, "options": [{"name": "서버", "type": 3, "value": "ju", "focused": True}]},
                     client, itype=discord.InteractionType.autocomplete)
    check(await tree.interaction_check(it) is False and it.response.autocompleted == [], "자동완성 조용히 차단")

    client2 = discord.Client(intents=discord.Intents.default())
    tree2 = PermissionTree(client2)  # permissions 없음
    try:
        await tree2.interaction_check(interaction(OWNER, start, client2))
        check(False, "권한 관리자 없으면 막혀야 함")
    except InsufficientLevel:
        check(True, "권한 관리자 없음 → 전부 차단(fail-closed)")

    await client.close(); await client2.close()

asyncio.run(run_gate_tests())

print(f"\n{count - len(failures)}/{count} 통과")
sys.exit(1 if failures else 0)
