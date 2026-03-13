from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1]


def run_manage(*args: str, env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=API_DIR,
        check=True,
        env=env,
    )


def main() -> None:
    env = os.environ.copy()
    env.setdefault("DJANGO_DEBUG", "true")
    env.setdefault("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
    port = env.get("E2E_API_PORT", "8001")
    web_port = env.get("E2E_WEB_PORT", "4173")
    env.setdefault(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        f"http://127.0.0.1:{web_port},http://localhost:{web_port}",
    )

    run_manage("migrate", "--noinput", env=env)
    run_manage("seed_e2e_data", env=env)
    run_manage("runserver", f"127.0.0.1:{port}", "--noreload", env=env)


if __name__ == "__main__":
    main()
