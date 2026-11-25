"""
실제 운영 봇 (본가 데스크톱, 친구들이 쓰는 봇)
경로: run_prod.py
설정: profiles/prod.py
"""

import settings

settings.activate("prod")

from bot import main  # noqa: E402  (activate 다음에 import 해야 설정이 반영됨)

if __name__ == "__main__":
    main()
