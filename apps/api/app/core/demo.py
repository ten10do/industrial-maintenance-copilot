"""演示账号识别。"""

from __future__ import annotations

DEMO_EMAIL_DOMAIN = "example.com"


def is_demo_account(email: str) -> bool:
    """识别种子数据使用的保留域名账号。"""

    return email.strip().casefold().endswith(f"@{DEMO_EMAIL_DOMAIN}")
