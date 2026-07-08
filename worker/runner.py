from __future__ import annotations

import sys
import time

from app.db.base import init_db
from app.services.seed_importer import import_seed_data


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "import-seed":
        init_db()
        summary = import_seed_data()
        print(summary)
        return 0
    if command == "healthcheck":
        print("ok")
        return 0
    if command == "serve":
        init_db()
        while True:
            time.sleep(3600)
    print(f"unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
