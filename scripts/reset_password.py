"""重置本地用户密码（在项目根目录执行）。

用法:
  python scripts/reset_password.py <用户名> <新密码>

示例:
  python scripts/reset_password.py admin admin123
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    username, password = sys.argv[1].strip(), sys.argv[2]
    if len(username) < 2:
        print("用户名至少 2 个字符")
        return 1
    if len(password) < 6:
        print("密码至少 6 位")
        return 1

    from core.database.db import get_db
    from core.security.users import hash_password

    db = get_db()
    row = db.get_user_by_username(username)
    if not row:
        print(f"用户不存在: {username}")
        print("已有用户请用管理页创建；若无任何用户，请重启服务并配置 bootstrap_admin。")
        return 1
    db.update_user(row["id"], password_hash=hash_password(password))
    print(f"已重置用户「{username}」的密码，请重新登录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
