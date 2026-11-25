"""
모든 테스트 실행
실행: python tests/run_all.py

각 테스트를 별도 프로세스로 돌립니다 (settings.activate() 는 프로세스당 한 번만 가능해서).
디스코드 접속 없음, 실제 서버 폴더·권한 파일은 건드리지 않음.
"""

import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parent

TESTS = [
    "test_permissions.py",
    "test_integration.py",
    "test_process.py",      # 가짜 서버 프로세스를 실제로 띄움 (Windows 에선 최소화 창이 잠깐씩 뜸)
]


def main() -> int:
    failed = []
    for name in TESTS:
        print(f"\n{'=' * 60}\n▶ {name}\n{'=' * 60}")
        result = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(TESTS_DIR / name), str(REPO)],  # -X utf8: Windows 파이프 출력도 UTF-8
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out_lines = result.stdout.strip().splitlines()
        # 요약만: FAIL 줄 + "N/M 통과" 줄
        for line in out_lines:
            if "FAIL" in line:
                print(line)
        summary = next((l for l in reversed(out_lines) if l.endswith("통과")), None)
        print(summary or "(통과 수 출력 없음 — 테스트가 중간에 죽었을 수 있음)")
        # stderr 는 실패했을 때만 (screen 미설치 같은 무해한 로그가 섞일 수 있어서)
        if result.returncode != 0 or summary is None:
            failed.append(name)
            print("--- 출력 끝부분 ---")
            print("\n".join(out_lines[-20:]))
            if result.stderr.strip():
                print("--- stderr ---")
                print("\n".join(result.stderr.strip().splitlines()[-30:]))

    print(f"\n{'=' * 60}")
    if failed:
        print(f"❌ 실패: {', '.join(failed)}  (자세히: python tests/<파일명>)")
        return 1
    print("✅ 전체 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
