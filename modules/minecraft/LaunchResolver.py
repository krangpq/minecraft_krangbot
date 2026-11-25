"""
서버 시작 명령 결정 (Forge/NeoForge 서버팩, 일반 jar, 직접 지정)
경로: modules/minecraft/LaunchResolver.py

결정 순서
  1. bot_config.json 의 "launch": {"args": [...]}   (java 뒤에 붙는 인자를 직접 지정)
  2. Forge / NeoForge args 파일  (run.bat 이 가리키는 libraries/.../win_args.txt)
     → java @user_jvm_args.txt @libraries/.../win_args.txt nogui
     서버팩 루트의 server.jar(ServerStarterJar, 설치 도우미)나 installer jar 는 쓰지 않음
  3. Fabric  (fabric-server-launch.jar) → java -Xms -Xmx -jar fabric-server-launch.jar nogui
     MC 버전은 .fabric/server/fabric-loader-server-<로더>-minecraft-<MC>.jar 또는 versions/<MC>/ 에서 읽음
  4. 일반 jar  (server.jar 우선, *installer*.jar 제외)
     → java -Xms -Xmx -jar X nogui

메모리(-Xmx)는 한 곳에서만 관리
  - Forge/NeoForge: user_jvm_args.txt (봇은 읽기만 함, bot_config 의 memory 는 무시)
  - 일반 jar / Fabric: bot_config.json 의 memory
    (bot_config 에 없으면 start.bat·run.bat 의 -Xms/-Xmx 를 읽음 → 첫 스캔 때 bot_config 로 옮겨 적음)
  - 직접 지정: launch.args 안의 -Xmx (또는 거기서 참조하는 @user_jvm_args.txt)

java 실행 파일은 run.bat 처럼 PATH 의 java 를 그대로 쓰지 않고
MC 버전에 맞는 버전을 고름 (select_java 참고).
"""

import os
import re
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IS_WINDOWS = platform.system() == "Windows"
ARGS_FILE_NAME = "win_args.txt" if IS_WINDOWS else "unix_args.txt"
RUN_SCRIPT_NAME = "run.bat" if IS_WINDOWS else "run.sh"

# libraries 아래 로더별 args 파일 위치
LOADER_DIRS = (
    ("neoforge", Path("libraries/net/neoforged/neoforge")),
    ("forge", Path("libraries/net/minecraftforge/forge")),
)


@dataclass
class LaunchPlan:
    kind: str                         # "custom" / "forge" / "neoforge" / "fabric" / "jar"
    args: List[str]                   # java 다음에 오는 인자 전부
    mc_version: Optional[str] = None  # 예: "1.20.1" (모르면 None)
    loader_version: Optional[str] = None
    memory_min_mb: Optional[int] = None
    memory_max_mb: Optional[int] = None
    memory_source: Optional[str] = None   # "user_jvm_args.txt" / "bot_config.json" / "launch.args" / "start.bat" / "기본값"
    jar_file: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def describe(self) -> str:
        loader = {"forge": "Forge", "neoforge": "NeoForge", "fabric": "Fabric", "jar": "jar",
                  "custom": "직접 지정"}[self.kind]
        ver = f" {self.mc_version}" if self.mc_version else ""
        lv = f"-{self.loader_version}" if self.loader_version and self.kind in ("forge", "neoforge", "fabric") else ""
        return f"{loader}{ver}{lv}"


# ============================================
# 메모리
# ============================================

_MEM_RE = re.compile(r"^-Xm([sx])(\d+)([kKmMgGtT]?)$")


def _to_mb(number: str, unit: str) -> int:
    n = int(number)
    unit = unit.lower()
    if unit == "k":
        return n // 1024
    if unit == "m":
        return n
    if unit == "g":
        return n * 1024
    if unit == "t":
        return n * 1024 * 1024
    return n // (1024 * 1024)  # 단위 없음 = 바이트


def parse_memory_args(tokens: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """['-Xms8G', '-Xmx16G'] → (8192, 16384). 여러 번 나오면 마지막 값 (JVM 과 같은 규칙)"""
    xms = xmx = None
    for tok in tokens:
        m = _MEM_RE.match(tok.strip())
        if not m:
            continue
        mb = _to_mb(m.group(2), m.group(3))
        if m.group(1) == "s":
            xms = mb
        else:
            xmx = mb
    return xms, xmx


def read_args_file(path: Path) -> List[str]:
    """user_jvm_args.txt 같은 @파일: 주석(#) 줄 빼고 공백으로 나눈 토큰"""
    tokens = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens.extend(line.split())
    except OSError:
        pass
    return tokens


def _memory_from_args(server_path: Path, args: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """인자 목록 + 거기서 참조하는 @파일(서버 폴더 기준)까지 펼쳐서 메모리 읽기"""
    tokens = []
    for a in args:
        if a.startswith("@"):
            tokens.extend(read_args_file(server_path / a[1:]))
        else:
            tokens.append(a)
    return parse_memory_args(tokens)


# ============================================
# MC 버전 / 필요한 Java 버전
# ============================================

def mc_version_from_loader(kind: str, loader_dir_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    forge   '1.20.1-47.4.22' → ('1.20.1', '47.4.22')
    neoforge '21.1.248'      → ('1.21.1', '21.1.248')   (NeoForge 버전 앞 두 자리 = MC 1.x.y)
    """
    if kind == "forge":
        if "-" in loader_dir_name:
            mc, lv = loader_dir_name.split("-", 1)
            return mc, lv
        return None, loader_dir_name
    if kind == "neoforge":
        parts = loader_dir_name.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            major, minor = int(parts[0]), int(parts[1])
            if major < 26:  # 20.x, 21.x = 1.20.x, 1.21.x 체계
                mc = f"1.{major}" if minor == 0 else f"1.{major}.{minor}"
                return mc, loader_dir_name
        return None, loader_dir_name
    return None, None


def required_java_major(mc_version: Optional[str]) -> Optional[int]:
    """MC 버전별 최소 Java (모르면 None)"""
    if not mc_version:
        return None
    try:
        parts = tuple(int(p) for p in mc_version.split(".")[:3])
    except ValueError:
        return None
    if parts[0] >= 26:
        # 2026년부터 연도 기반 버전 (26.1, 26.3 …) → Java 25
        # (실제 withher 서버: start.bat 에 "requires Java 25", 로그에 java 25)
        return 25
    if parts < (1, 17):
        return 8
    if parts < (1, 18):
        return 16
    if parts < (1, 20, 5):
        return 17
    return 21


# ============================================
# Java 찾기
# ============================================

def _java_exe_name() -> str:
    return "java.exe" if IS_WINDOWS else "java"


def _read_release_major(java_home: Path) -> Optional[int]:
    """JDK 폴더의 release 파일 JAVA_VERSION="17.0.19" → 17 ("1.8.0_x" → 8)"""
    release = java_home / "release"
    try:
        for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("JAVA_VERSION="):
                v = line.split("=", 1)[1].strip().strip('"')
                first = v.split(".")[0]
                if first == "1" and len(v.split(".")) > 1:
                    return int(v.split(".")[1])
                return int(first)
    except (OSError, ValueError):
        pass
    return None


def _candidate_java_homes() -> List[Path]:
    homes = []
    roots = []
    if IS_WINDOWS:
        for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                for vendor in ("Eclipse Adoptium", "Java", "Microsoft", "Zulu", "BellSoft", "Amazon Corretto", "Semeru"):
                    roots.append(Path(base) / vendor)
    else:
        roots += [Path("/usr/lib/jvm"), Path("/opt/java")]
    home = Path.home()
    roots += [home / ".jabba" / "jdk", home / ".jdks"]
    seen = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                key = str(child).lower()
                if key in seen:
                    continue
                seen.add(key)
                if (child / "bin" / _java_exe_name()).exists():
                    homes.append(child)
        except OSError:
            continue
    return homes


_detect_cache: Optional[Dict[int, str]] = None


def detect_installed_javas(refresh: bool = False) -> Dict[int, str]:
    """{주버전: java 실행 파일 경로}. 같은 주버전이 여러 개면 경로 이름순 마지막(보통 최신)"""
    global _detect_cache
    if _detect_cache is not None and not refresh:
        return dict(_detect_cache)
    found: Dict[int, List[str]] = {}
    for h in _candidate_java_homes():
        major = _read_release_major(h)
        if major:
            found.setdefault(major, []).append(str(h / "bin" / _java_exe_name()))
    _detect_cache = {m: sorted(paths)[-1] for m, paths in found.items()}
    return dict(_detect_cache)


def select_java(required: Optional[int],
                explicit: Optional[str] = None,
                java_paths: Optional[dict] = None,
                auto_detect: bool = True,
                default_java: str = "java",
                installed: Optional[Dict[int, str]] = None) -> Tuple[str, str]:
    """
    Returns: (java 경로, 고른 이유)
    규칙: 직접 지정 > JAVA_PATHS > 자동 감지 > 기본값. 버전은 '필요 버전 이상 중 가장 낮은 것'
    (1.20.1 Forge 에 25 를 쓰면 안 돌아가는 모드가 있을 수 있어서 가장 가까운 버전을 고름)
    """
    if explicit:
        return explicit, "bot_config.json 지정"

    def pick(table: Dict[int, str], source: str) -> Optional[Tuple[str, str]]:
        usable = sorted(m for m in table if required is None or m >= required)
        if not usable:
            return None
        major = usable[0]
        return table[major], f"{source} Java {major}"

    if required is not None:
        if java_paths:
            table = {}
            for k, v in java_paths.items():
                try:
                    table[int(k)] = str(v)
                except (TypeError, ValueError):
                    continue
            r = pick(table, "JAVA_PATHS")
            if r:
                return r
        if auto_detect:
            table = installed if installed is not None else detect_installed_javas()
            r = pick(table, "자동 감지")
            if r:
                return r
        reason = f"Java {required} 이상을 못 찾아서 기본값 사용"
    else:
        reason = "MC 버전을 몰라서 기본값 사용"

    resolved = shutil.which(default_java) or default_java
    return resolved, reason


# ============================================
# 시작 명령
# ============================================

def _args_file_from_run_script(server_path: Path) -> Optional[str]:
    """run.bat / run.sh 의 java 줄에서 @libraries/.../win_args.txt 경로"""
    script = server_path / RUN_SCRIPT_NAME
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = re.search(r"@(libraries[/\\]\S+?" + re.escape(ARGS_FILE_NAME) + r")", line)
        if m and not line.strip().lower().startswith(("rem", "::", "#")):
            return m.group(1).replace("\\", "/")
    return None


def _version_key(name: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", name)]


def find_loader_args(server_path: Path) -> Optional[Tuple[str, str, str, List[str]]]:
    """
    Returns: (kind, args 파일 상대 경로, 로더 버전 폴더 이름, 경고) 또는 None
    """
    warnings = []
    from_script = _args_file_from_run_script(server_path)
    if from_script and (server_path / from_script).exists():
        rel = Path(from_script)
        for kind, base in LOADER_DIRS:
            try:
                rest = rel.relative_to(base)
                return kind, from_script, rest.parts[0], warnings
            except ValueError:
                continue
        return "forge", from_script, rel.parent.name, warnings
    if from_script:
        warnings.append(f"{RUN_SCRIPT_NAME} 가 가리키는 {from_script} 가 없음 → libraries 에서 찾음")

    for kind, base in LOADER_DIRS:
        d = server_path / base
        if not d.is_dir():
            continue
        versions = sorted((v for v in d.iterdir() if (v / ARGS_FILE_NAME).exists()),
                          key=lambda v: _version_key(v.name))
        if not versions:
            continue
        if len(versions) > 1:
            warnings.append(f"{base} 에 버전이 여러 개라 가장 높은 {versions[-1].name} 사용")
        chosen = versions[-1]
        rel = (base / chosen.name / ARGS_FILE_NAME).as_posix()
        return kind, rel, chosen.name, warnings
    return None


SCRIPT_NAMES = ("start.bat", "run.bat", "start.cmd", "start.sh", "run.sh")


def memory_from_scripts(server_path: Path) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """start.bat / run.bat 의 java 줄에서 -Xms/-Xmx (주석 줄 제외). Returns (xms, xmx, 파일 이름)"""
    for name in SCRIPT_NAMES:
        f = server_path / name
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            low = line.strip().lower()
            if not low or low.startswith(("rem", "::", "#", "echo")) or "-xmx" not in low:
                continue
            xms, xmx = parse_memory_args([t.strip('"') for t in line.split()])
            if xmx:
                return xms, xmx, name
    return None, None, None


FABRIC_LAUNCHERS = ("fabric-server-launch.jar", "fabric-server-launcher.jar")


def find_fabric(server_path: Path) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Returns (런처 jar, MC 버전, 로더 버전) 또는 None"""
    launcher = next((n for n in FABRIC_LAUNCHERS if (server_path / n).exists()), None)
    if not launcher:
        return None
    mc = loader = None
    srv = server_path / ".fabric" / "server"
    if srv.is_dir():
        for f in sorted(srv.glob("fabric-loader-server-*-minecraft-*.jar")):
            m = re.match(r"fabric-loader-server-(.+)-minecraft-(.+)\.jar$", f.name)
            if m:
                loader, mc = m.group(1), m.group(2)
    if mc is None and (server_path / "versions").is_dir():
        vers = sorted((v.name for v in (server_path / "versions").iterdir() if v.is_dir()), key=_version_key)
        if vers:
            mc = vers[-1]
    return launcher, mc, loader


def find_plain_jar(server_path: Path) -> Optional[str]:
    jars = sorted(p.name for p in server_path.glob("*.jar") if "installer" not in p.name.lower())
    if not jars:
        return None
    for name in jars:
        if name.lower() == "server.jar":
            return name
    return jars[0]


def resolve_launch(server_path: Path, bot_config: dict,
                   default_min_mb: int, default_max_mb: int) -> Tuple[Optional[LaunchPlan], str]:
    """
    Returns: (LaunchPlan, 메시지) — 실행할 방법이 없으면 (None, 이유)
    """
    server_path = Path(server_path)
    bot_config = bot_config or {}

    # 1. 직접 지정
    launch = bot_config.get("launch")
    if isinstance(launch, dict) and launch.get("args"):
        args = launch["args"]
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return None, "bot_config.json 의 launch.args 는 문자열 목록이어야 합니다"
        xms, xmx = _memory_from_args(server_path, args)
        plan = LaunchPlan(kind="custom", args=list(args),
                          mc_version=launch.get("mc_version"),
                          memory_min_mb=xms, memory_max_mb=xmx,
                          memory_source="launch.args" if xmx else None)
        return plan, "bot_config.json 의 launch.args 사용"

    # 2. Forge / NeoForge
    found = find_loader_args(server_path)
    if found:
        kind, args_rel, loader_dir, warnings = found
        mc, lv = mc_version_from_loader(kind, loader_dir)
        args = []
        jvm_args = server_path / "user_jvm_args.txt"
        if jvm_args.exists():
            args.append("@user_jvm_args.txt")
        else:
            warnings.append("user_jvm_args.txt 가 없어 메모리(-Xmx)가 JVM 기본값이 됩니다")
        args += [f"@{args_rel}", "nogui"]
        xms, xmx = parse_memory_args(read_args_file(jvm_args)) if jvm_args.exists() else (None, None)
        if isinstance(bot_config.get("memory"), dict) and bot_config["memory"] and jvm_args.exists():
            # 메모리는 user_jvm_args.txt 한 곳에서만 → bot_config 값은 안 씀
            bm = bot_config["memory"].get("max")
            if bm and xmx and bm != xmx:
                warnings.append(f"bot_config.json memory.max({bm}MB)는 무시됨 — user_jvm_args.txt 의 -Xmx({xmx}MB) 사용")
        plan = LaunchPlan(kind=kind, args=args, mc_version=mc, loader_version=lv,
                          memory_min_mb=xms, memory_max_mb=xmx,
                          memory_source="user_jvm_args.txt" if xmx else None,
                          warnings=warnings)
        return plan, f"{plan.describe()} args 파일 사용"

    # 3. Fabric / 4. 일반 jar
    fabric = find_fabric(server_path)
    if fabric:
        jar, mc, loader = fabric
        kind = "fabric"
    else:
        jar, mc, loader = find_plain_jar(server_path), None, None
        kind = "jar"
    if jar:
        mem = bot_config.get("memory") or {}
        if mem.get("max"):
            xms = int(mem.get("min") or default_min_mb)
            xmx = int(mem["max"])
            source = "bot_config.json"
        else:
            s_xms, s_xmx, script = memory_from_scripts(server_path)
            if s_xmx:
                xms, xmx, source = (s_xms or min(default_min_mb, s_xmx)), s_xmx, script
            else:
                xms, xmx, source = default_min_mb, default_max_mb, "기본값"
        xms = min(xms, xmx)
        plan = LaunchPlan(kind=kind, args=[f"-Xms{xms}M", f"-Xmx{xmx}M", "-jar", jar, "nogui"],
                          mc_version=bot_config.get("mc_version") or mc, loader_version=loader,
                          memory_min_mb=xms, memory_max_mb=xmx, memory_source=source,
                          jar_file=jar)
        return plan, f"{jar} 실행"

    return None, "실행할 방법을 찾지 못했습니다 (Forge/NeoForge args 파일도, 서버 jar 도 없음)"
