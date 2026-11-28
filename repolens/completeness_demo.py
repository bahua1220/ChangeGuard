"""A separate synthetic repository with positive and negative check scenarios."""

import os
from pathlib import Path
import subprocess


DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data/completeness_demo_repository"


def create_completeness_demo(path=DEFAULT_PATH):
    root = Path(path).resolve()
    marker = root / ".git/changeguard-completeness-demo-v1"
    if marker.is_file():
        return str(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("遗漏检测演示目录非空且不是完整演示仓库，请选择新目录。")
    root.mkdir(parents=True, exist_ok=True)

    def command(*args, env=None):
        proc = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "-C", str(root), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=env)
        if proc.returncode:
            raise RuntimeError("无法创建遗漏检测演示：" + proc.stderr.strip())

    index = 0

    def commit(message, files):
        nonlocal index
        index += 1
        for name, content in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        env = {**os.environ, "GIT_AUTHOR_NAME": "ChangeGuard Demo", "GIT_AUTHOR_EMAIL": "demo@example.test",
               "GIT_COMMITTER_NAME": "ChangeGuard Demo", "GIT_COMMITTER_EMAIL": "demo@example.test",
               "GIT_AUTHOR_DATE": f"2026-11-28T08:{index:02d}:00+08:00", "GIT_COMMITTER_DATE": f"2026-11-28T08:{index:02d}:00+08:00"}
        command("add", "--all")
        command("commit", "-m", message, env=env)

    command("init", "--initial-branch=main")
    commit("demo: initialize synthetic completeness fixture", {"src/auth.py": "POLICY = 0\n", "tests/test_auth.py": "EXPECTED_POLICY = 0\n", "src/cache.py": "CACHE_VERSION = 0\n"})
    for revision in range(1, 5):
        commit(f"demo: update auth and tests together {revision}", {"src/auth.py": f"POLICY = {revision}\n", "tests/test_auth.py": f"EXPECTED_POLICY = {revision}\n"})
    for revision in range(1, 8):
        commit(f"demo: independent cache update {revision}", {"src/cache.py": f"CACHE_VERSION = {revision}\n"})
    commit("demo: auth-only change (missing test update)", {"src/auth.py": "POLICY = 5\n"})
    commit("demo: complete auth and test change", {"src/auth.py": "POLICY = 6\n", "tests/test_auth.py": "EXPECTED_POLICY = 6\n"})
    commit("demo: unrelated cache-only change", {"src/cache.py": "CACHE_VERSION = 8\n"})
    marker.write_text("Synthetic demonstration, not team development evidence.\n", encoding="utf-8")
    return str(root)
