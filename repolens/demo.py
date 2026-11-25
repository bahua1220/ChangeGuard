"""Create an explicitly synthetic, deterministic Git repository for demos/tests."""

import os
import subprocess
from pathlib import Path

DEFAULT_DEMO = Path(__file__).resolve().parents[1] / "data" / "demo_repository"


def create_demo(path=DEFAULT_DEMO):
    root = Path(path).resolve()
    if (root / ".git").is_dir():
        return str(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("演示仓库目录非空，无法创建。")
    root.mkdir(parents=True, exist_ok=True)

    def command(*args, env=None):
        result = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "-C", str(root), *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if result.returncode:
            raise RuntimeError("演示仓库 Git 操作失败：" + result.stderr.strip())

    def commit(message, author, day, hour, files, deletes=(), moves=()):
        for source, target in moves:
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            (root / source).rename(root / target)
        for name in deletes:
            (root / name).unlink()
        for name, contents in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8", newline="\n")
        env = os.environ.copy()
        env.update({"GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": author.lower() + "@example.test",
                    "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": author.lower() + "@example.test",
                    "GIT_AUTHOR_DATE": f"2026-11-{day:02d}T{hour:02d}:00:00+08:00",
                    "GIT_COMMITTER_DATE": f"2026-11-{day:02d}T{hour:02d}:00:00+08:00"})
        command("add", "--all")
        command("commit", "-m", message, env=env)

    command("init", "--initial-branch=main")
    commit("docs: initialize synthetic Atlas project", "Alice", 9, 9, {"README.md": "# Atlas\nSynthetic repository for RepoLens demos.\n", ".gitignore": "__pycache__/\n.env\n"})
    commit("feat: add repository metadata reader", "Alice", 10, 10, {"src/mining/reader.py": "def read_metadata(repo):\n    return {'name': repo.name}\n", "tests/test_reader.py": "def test_metadata():\n    assert 'name' in {'name': 'atlas'}\n"})
    commit("feat: introduce dashboard layout", "Bob", 10, 14, {"src/ui/dashboard.py": "TITLE = 'Atlas'\n\ndef render(data):\n    return {'title': TITLE, 'data': data}\n"})
    commit("feat: add SQLite commit cache", "Chen", 11, 10, {"src/storage/cache.py": "import sqlite3\n\ndef connect(path):\n    return sqlite3.connect(path)\n"})
    commit("feat: extract commit author and timestamp", "Alice", 11, 16, {"src/mining/reader.py": "def read_metadata(repo):\n    return {'name': repo.name}\n\ndef read_commit(commit):\n    return {'hash': commit.hexsha, 'author': commit.author.name,\n            'timestamp': commit.committed_datetime.isoformat()}\n"})
    commit("feat: visualize daily commit activity", "Bob", 12, 11, {"src/ui/timeline.py": "def daily_counts(commits):\n    counts = {}\n    for commit in commits:\n        day = commit['timestamp'][:10]\n        counts[day] = counts.get(day, 0) + 1\n    return counts\n", "src/ui/dashboard.py": "from .timeline import daily_counts\n\nTITLE = 'Atlas'\n\ndef render(data):\n    return {'title': TITLE, 'timeline': daily_counts(data)}\n"})
    commit("test: cover empty metadata input", "Chen", 12, 15, {"tests/test_reader.py": "def test_metadata():\n    assert 'name' in {'name': 'atlas'}\n\ndef test_empty():\n    assert list([]) == []\n"})
    commit("fix: reject missing repository metadata", "Alice", 13, 9, {"src/mining/reader.py": "def read_metadata(repo):\n    if repo is None:\n        raise ValueError('Repository is required')\n    return {'name': repo.name}\n\ndef read_commit(commit):\n    return {'hash': commit.hexsha, 'author': commit.author.name,\n            'timestamp': commit.committed_datetime.isoformat()}\n"})
    commit("feat: add file change ranking", "Bob", 14, 10, {"src/ui/files.py": "from collections import Counter\n\ndef file_ranking(changes):\n    return Counter(item['path'] for item in changes).most_common()\n"})
    command("tag", "v0.1.0")
    commit("feat: persist cached commit records", "Chen", 15, 10, {"src/storage/cache.py": "import sqlite3\n\ndef connect(path):\n    connection = sqlite3.connect(path)\n    connection.execute('CREATE TABLE IF NOT EXISTS commits (hash TEXT PRIMARY KEY, message TEXT)')\n    return connection\n\ndef save(connection, sha, message):\n    with connection:\n        connection.execute('INSERT OR REPLACE INTO commits VALUES (?, ?)', (sha, message))\n"})
    commit("feat: add date-range filtering", "Alice", 16, 9, {"src/mining/filters.py": "def in_range(commit, start, end):\n    return start <= commit['timestamp'][:10] <= end\n"})
    commit("feat: add developer activity table", "Bob", 16, 14, {"src/ui/developers.py": "from collections import Counter\n\ndef activity(commits):\n    return Counter(item['author'] for item in commits)\n"})
    commit("feat: build evidence-linked report", "Chen", 17, 10, {"src/reports/summary.py": "def evidence(commits):\n    return [{'hash': c['hash'], 'message': c['message']} for c in commits]\n"})
    commit("refactor: rename metadata reader module", "Alice", 18, 10, {}, moves=[("src/mining/reader.py", "src/mining/extractor.py")])
    commit("docs: document sprint review workflow", "Chen", 19, 11, {"docs/sprint-review.md": "# Sprint review\nSelect a branch and date range.\nReview charts, inspect diffs and verify report evidence.\n", "README.md": "# Atlas\nSynthetic repository for RepoLens demos.\n\nIncludes mining, a dashboard, caching and report evidence.\n"})
    commit("fix: sort timeline dates before rendering", "Bob", 20, 10, {"src/ui/timeline.py": "def daily_counts(commits):\n    counts = {}\n    for commit in commits:\n        day = commit['timestamp'][:10]\n        counts[day] = counts.get(day, 0) + 1\n    return dict(sorted(counts.items()))\n"})
    commit("chore: remove obsolete metadata test", "Alice", 21, 10, {}, deletes=["tests/test_reader.py"])
    commit("feat: export sprint report as Markdown", "Chen", 22, 10, {"src/reports/export.py": "def to_markdown(report):\n    return '# Sprint report\\n\\n' + '\\n'.join(report)\n", "docs/sprint-review.md": "# Sprint review\nSelect a branch and date range.\nReview charts, inspect diffs and verify report evidence.\nDownload the final report as Markdown.\n"})
    command("tag", "v0.2.0")
    command("branch", "sprint-1", "v0.1.0")
    return str(root)


if __name__ == "__main__":
    print(create_demo())
