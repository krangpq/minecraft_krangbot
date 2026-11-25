"""
테스트 봇 (노트북 등 개발용, 실제 봇과 토큰 분리)
경로: run_dev.py
설정: profiles/dev.py
"""

import settings

settings.activate("dev")

from bot import main  # noqa: E402  (activate 다음에 import 해야 설정이 반영됨)

if __name__ == "__main__":
    main()
