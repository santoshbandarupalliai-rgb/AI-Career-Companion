"""Delete demo/test accounts (emails ending in -e2e@example.com) and their uploaded files.

Run from the repo root:   backend\\.venv\\Scripts\\python backend\\scripts\\delete_e2e_users.py
Deleting a user cascades to every row that user owns. Other accounts are never touched.
"""

import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402

PATTERN = "%-e2e@example.com"


def main() -> None:
    with engine.begin() as conn:
        ids = [str(r[0]) for r in conn.execute(text("SELECT id FROM users WHERE email LIKE :p"), {"p": PATTERN})]
        n = conn.execute(text("DELETE FROM users WHERE email LIKE :p"), {"p": PATTERN}).rowcount
    for uid in ids:
        shutil.rmtree(BACKEND / "uploads" / uid, ignore_errors=True)
    print(f"Deleted {n} demo account(s).")


if __name__ == "__main__":
    main()
