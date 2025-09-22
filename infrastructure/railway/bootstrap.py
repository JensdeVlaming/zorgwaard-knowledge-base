"""Railway bootstrap helper to run pending database migrations."""
from __future__ import annotations

from core.db_client import init_db


def main() -> None:
    init_db()


if __name__ == "__main__":
    main()
