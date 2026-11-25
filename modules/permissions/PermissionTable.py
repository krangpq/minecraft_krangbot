"""
권한 등급 정의 + 명령어별 필요 등급 표
경로: modules/permissions/PermissionTable.py

명령어 권한을 바꾸고 싶으면 이 파일의 COMMAND_LEVELS / OPTION_LEVELS만 고치면 됩니다.
표에 없는 명령어는 DEFAULT_LEVEL(소유자 전용)로 막힙니다 → 새 명령어를 추가하고
표에 안 넣으면 봇 시작 시 경고가 뜹니다.
"""

from enum import IntEnum
from typing import Dict, Iterable, Optional, Tuple


class Level(IntEnum):
    GUEST = 0     # 미등록 (화이트리스트에 없음)
    MEMBER = 1    # 멤버: 조회만
    OPERATOR = 2  # 운영자: 켜기/끄기/재시작/백업
    ADMIN = 3     # 관리자: 콘솔 명령, 서버 구성 변경, 권한 관리(운영자까지)
    OWNER = 4     # 소유자: config.BOT_OWNER_ID 고정, 명령어로 부여 불가


LEVEL_NAMES: Dict[Level, str] = {
    Level.GUEST: "미등록",
    Level.MEMBER: "멤버",
    Level.OPERATOR: "운영자",
    Level.ADMIN: "관리자",
    Level.OWNER: "소유자",
}

# 표에 없는 명령어의 필요 등급 (fail-closed)
DEFAULT_LEVEL = Level.OWNER

# 명령어 qualified name → 필요 등급
# 그룹 하위 명령어는 "그룹 하위명" 형태 (예: "권한 부여")
COMMAND_LEVELS: Dict[str, Level] = {
    # ── 누구나 ──────────────────────────────
    "내아이디": Level.GUEST,
    "내권한": Level.GUEST,

    # ── 멤버: 조회 ──────────────────────────
    "서버상태": Level.MEMBER,
    "서버목록": Level.MEMBER,
    "구동기목록": Level.MEMBER,
    "플러그인목록": Level.MEMBER,
    "spigot빌드상태": Level.MEMBER,
    "스크린정보": Level.MEMBER,

    # ── 운영자: 켜기/끄기 ───────────────────
    "서버시작": Level.OPERATOR,
    "서버중지": Level.OPERATOR,
    "서버재시작": Level.OPERATOR,
    "백업": Level.OPERATOR,

    # ── 관리자: 서버 구성 변경 ──────────────
    "명령어실행": Level.ADMIN,
    "서버생성": Level.ADMIN,
    "서버업그레이드": Level.ADMIN,
    "서버롤백": Level.ADMIN,
    "플러그인추가": Level.ADMIN,
    "모드추가": Level.ADMIN,
    "구동기업데이트": Level.ADMIN,
    "백업정리": Level.ADMIN,

    # ── 관리자: 권한 관리 (자기보다 낮은 등급까지만) ──
    "권한 목록": Level.ADMIN,
    "권한 부여": Level.ADMIN,
    "권한 회수": Level.ADMIN,

    # ── 소유자 전용 ─────────────────────────
    "서버삭제": Level.OWNER,
}

# 특정 옵션을 켰을 때만 더 높은 등급 요구: (명령어, 옵션명) → 필요 등급
# 옵션 값이 참(True/비어있지 않음)일 때만 적용
OPTION_LEVELS: Dict[Tuple[str, str], Level] = {
    ("서버중지", "강제"): Level.ADMIN,  # 강제 종료는 월드 손상 위험
}

# Discord 옵션 타입: 1 = SUB_COMMAND, 2 = SUB_COMMAND_GROUP
_SUBCOMMAND_TYPES = (1, 2)


def resolve_command_path(data: dict) -> Tuple[str, list]:
    """
    인터랙션 data에서 ("그룹 하위명", 말단 옵션 리스트)를 뽑는다.
    discord.py 내부 캐시에 의존하지 않고 원본 payload만 사용.
    """
    parts = [data.get("name", "")]
    options = data.get("options") or []
    while options and options[0].get("type") in _SUBCOMMAND_TYPES:
        parts.append(options[0].get("name", ""))
        options = options[0].get("options") or []
    return " ".join(parts), options


def requirement(qualified_name: str, options: Iterable[dict] = ()) -> Tuple[Level, Optional[str]]:
    """
    명령어 + 실제로 넘어온 옵션 기준 필요 등급.
    반환: (필요 등급, 등급을 올린 옵션 이름 또는 None)
    """
    level = Level(COMMAND_LEVELS.get(qualified_name, DEFAULT_LEVEL))
    raised_by = None
    for opt in options:
        override = OPTION_LEVELS.get((qualified_name, opt.get("name")))
        if override is not None and opt.get("value") and override > level:
            level = Level(override)
            raised_by = opt.get("name")
    return level, raised_by


def required_level(qualified_name: str, options: Iterable[dict] = ()) -> Level:
    return requirement(qualified_name, options)[0]


def josa(word: str, with_final: str, without_final: str) -> str:
    """
    받침 유무에 맞춰 조사 붙이기
    josa("관리자", "이라", "라") → "관리자라", josa("미등록", "이라", "라") → "미등록이라"
    """
    if not word:
        return word + without_final
    ch = word[-1]
    if "가" <= ch <= "힣":
        final = (ord(ch) - 0xAC00) % 28
        # ㄹ 받침 + (으)로 → "로"
        if final == 8 and with_final == "으로":
            return word + without_final
        return word + (with_final if final else without_final)
    return word + without_final


def level_label(level: int) -> str:
    try:
        return LEVEL_NAMES[Level(level)]
    except ValueError:
        return f"알 수 없음({level})"
