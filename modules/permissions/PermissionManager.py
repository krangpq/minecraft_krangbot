"""
화이트리스트 저장소 + 등급 계산 + 부여/회수 규칙
경로: modules/permissions/PermissionManager.py

규칙
- 소유자(BOT_OWNER_ID)는 설정 파일에서만 정해지고, 명령어로 주거나 뺏을 수 없음
- 자기 등급보다 낮은 등급만 부여 가능 (관리자 → 운영자까지, 소유자 → 관리자까지)
- 자기와 같거나 높은 등급인 사람은 건드릴 수 없음, 자기 자신도 불가
- 디스코드 역할(role)은 보지 않음: 디스코드 서버 관리자가 역할을 줘서 화이트리스트를 우회하는 걸 막기 위함

저장
- JSON 파일, 임시 파일에 쓰고 교체(os.replace)하는 방식이라 쓰는 도중 전원이 나가도 기존 파일이 깨지지 않음
- 파일이 깨져 있으면 .corrupt-날짜 로 옮겨두고 빈 화이트리스트로 시작 (소유자만 사용 가능 = 안전한 쪽으로 실패)
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .PermissionTable import Level, josa, level_label, required_level

# 명령어로 부여 가능한 등급
GRANTABLE_LEVELS = (Level.MEMBER, Level.OPERATOR, Level.ADMIN)

# 부여/회수 자체에 필요한 등급은 권한표(/권한 부여, /권한 회수)를 그대로 따름 → 한 곳에서만 관리
GRANT_COMMAND = "권한 부여"
REVOKE_COMMAND = "권한 회수"


def _display_name(user) -> str:
    return getattr(user, "display_name", None) or getattr(user, "name", None) or str(user.id)


class PermissionManager:
    FILE_VERSION = 1

    def __init__(self, file_path: Path, owner_id: int):
        self.file_path = Path(file_path)
        self.owner_id = int(owner_id)
        self.users: Dict[int, dict] = {}
        self._load()

    # ============================================
    # 조회
    # ============================================

    def get_level(self, user) -> Level:
        """user: discord.User / discord.Member / .id 를 가진 객체 / int"""
        uid = int(getattr(user, "id", user))
        if uid == self.owner_id:
            return Level.OWNER
        entry = self.users.get(uid)
        if entry is None:
            return Level.GUEST
        return Level(entry["level"])

    def list_entries(self) -> List[Tuple[int, dict]]:
        """등급 높은 순 → 이름 순"""
        return sorted(
            self.users.items(),
            key=lambda item: (-item[1]["level"], item[1].get("name", "").lower())
        )

    # ============================================
    # 변경
    # ============================================

    def grant(self, actor, target, level: Level) -> Tuple[bool, str]:
        """target 에게 level 부여 (신규 등록 또는 등급 변경)"""
        level = Level(level)
        actor_level = self.get_level(actor)
        target_name = _display_name(target)

        needed = required_level(GRANT_COMMAND)
        if actor_level < needed:
            return False, f"권한 부여는 {level_label(needed)} 이상만 할 수 있어요."
        if getattr(target, "bot", False):
            return False, "봇 계정에는 권한을 줄 수 없어요."
        if int(target.id) == int(actor.id):
            return False, "자기 자신의 등급은 바꿀 수 없어요."
        if int(target.id) == self.owner_id:
            return False, "소유자 등급은 프로필 설정(BOT_OWNER_ID)에서만 정해져요."
        if level not in GRANTABLE_LEVELS:
            return False, "부여할 수 있는 등급은 멤버 / 운영자 / 관리자예요."
        if level >= actor_level:
            return False, (
                f"내 등급({level_label(actor_level)})보다 낮은 등급만 줄 수 있어요."
            )

        current = self.get_level(target)
        if current >= actor_level:
            return False, (
                f"{target_name}님은 {josa(level_label(current), '이라', '라')} 내 등급으로는 바꿀 수 없어요."
            )
        if current == level:
            return True, f"{target_name}님은 이미 {josa(level_label(level), '이에요', '예요')}."

        previous = self.users.get(int(target.id))
        self.users[int(target.id)] = {
            "level": int(level),
            "name": target_name,
            "granted_by": int(actor.id),
            "granted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        try:
            self._save()
        except OSError as e:
            self._restore(int(target.id), previous)
            return False, f"권한 파일 저장에 실패해서 변경을 취소했어요: {e}"

        print(
            f"[권한] {_display_name(actor)}({actor.id}) → {target_name}({target.id}): "
            f"{level_label(current)} → {level_label(level)}"
        )
        if current == Level.GUEST:
            return True, f"{target_name}님을 {josa(level_label(level), '으로', '로')} 등록했어요."
        return True, (
            f"{target_name}님 등급을 {level_label(current)} → {josa(level_label(level), '으로', '로')} 바꿨어요."
        )

    def revoke(self, actor, target) -> Tuple[bool, str]:
        """target 을 화이트리스트에서 제거"""
        actor_level = self.get_level(actor)
        target_name = _display_name(target)

        needed = required_level(REVOKE_COMMAND)
        if actor_level < needed:
            return False, f"권한 회수는 {level_label(needed)} 이상만 할 수 있어요."
        if int(target.id) == int(actor.id):
            return False, "자기 자신은 회수할 수 없어요."
        if int(target.id) == self.owner_id:
            return False, "소유자는 회수할 수 없어요."

        current = self.get_level(target)
        if current == Level.GUEST:
            return False, f"{target_name}님은 화이트리스트에 없어요."
        if current >= actor_level:
            return False, (
                f"{target_name}님은 {josa(level_label(current), '이라', '라')} 내 등급으로는 회수할 수 없어요."
            )

        previous = self.users.pop(int(target.id))
        try:
            self._save()
        except OSError as e:
            self._restore(int(target.id), previous)
            return False, f"권한 파일 저장에 실패해서 변경을 취소했어요: {e}"

        print(
            f"[권한] {_display_name(actor)}({actor.id}) → {target_name}({target.id}): "
            f"{level_label(current)} → 회수"
        )
        return True, f"{target_name}님의 권한({level_label(current)})을 회수했어요."

    def _restore(self, uid: int, previous):
        if previous is None:
            self.users.pop(uid, None)
        else:
            self.users[uid] = previous

    # ============================================
    # 파일 입출력
    # ============================================

    def _load(self):
        self.users = {}
        if not self.file_path.exists():
            print(f"[권한] 권한 파일 없음 → 빈 화이트리스트로 시작 ({self.file_path})")
            return

        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
            users_raw = raw.get("users") if isinstance(raw, dict) else None
            if not isinstance(users_raw, dict):
                raise ValueError("'users' 항목이 없거나 형식이 잘못됨")
        except (OSError, ValueError) as e:  # json.JSONDecodeError 는 ValueError
            self._quarantine(e)
            return

        for key, entry in users_raw.items():
            try:
                uid = int(key)
                level = int(entry["level"])
            except (KeyError, TypeError, ValueError):
                print(f"[권한] ⚠️ 잘못된 항목 무시: {key!r}: {entry!r}")
                continue
            if level not in [int(lv) for lv in GRANTABLE_LEVELS]:
                # 파일을 직접 고쳐 소유자(4) 등을 넣은 경우 포함
                print(f"[권한] ⚠️ 허용되지 않는 등급 무시: {key} → {level}")
                continue
            if uid == self.owner_id:
                continue  # 소유자는 파일과 무관하게 항상 소유자
            self.users[uid] = {**entry, "level": level}

        print(f"[권한] 화이트리스트 로드: {len(self.users)}명 ({self.file_path})")

    def _quarantine(self, error: Exception):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        moved_to = self.file_path.with_name(
            f"{self.file_path.stem}.corrupt-{stamp}{self.file_path.suffix}"
        )
        try:
            os.replace(self.file_path, moved_to)
            where = f"{moved_to} 로 옮겨뒀어요"
        except OSError as move_error:
            where = f"옮기지도 못했어요({move_error})"
        print(
            f"[권한] ❌ 권한 파일을 읽지 못했어요: {error}\n"
            f"       원본은 {where}.\n"
            f"       빈 화이트리스트로 시작합니다 → 소유자만 명령어를 쓸 수 있어요."
        )
        self.users = {}

    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.FILE_VERSION,
            "users": {str(uid): entry for uid, entry in sorted(self.users.items())},
        }

        fd, tmp_path = tempfile.mkstemp(
            prefix=f"{self.file_path.name}.", suffix=".tmp", dir=self.file_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self._replace_with_retry(tmp_path, self.file_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _replace_with_retry(src, dst, attempts: int = 5, delay: float = 0.1):
        """Windows에서 백신/인덱서가 잠깐 파일을 잡고 있으면 replace가 실패할 수 있어 몇 번 재시도"""
        for attempt in range(attempts):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(delay)
