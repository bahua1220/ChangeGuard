import json
import subprocess
from pathlib import Path

import pytest

from repolens import remote
from repolens.analytics import frames, metrics
from repolens.mining import ReadOnlyGit, RepositoryError, analysis_spec, git, inspect_repository, mine


@pytest.mark.parametrize("value", [
    "https://github.com/ishepard/pydriller", "https://github.com/ishepard/pydriller.git/",
    "github.com/ishepard/pydriller", " https://GitHub.com/ISHEPARD/PyDriller/ ",
])
def test_normalizes_repository_home_url(value):
    assert remote.normalize_github_url(value) == "https://github.com/ishepard/pydriller.git"


@pytest.mark.parametrize("value", [
    "", "D:/projects/repo", "file:///tmp/repo", "http://github.com/a/b",
    "https://example.com/a/b", "https://github.com.evil.test/a/b",
    "https://token@github.com/a/b", "https://github.com/a/b?token=secret",
    "https://github.com/a/b/tree/main", "https://github.com/a/b/blob/main/x.py",
    "https://github.com/a/..", "https://github.com/a/%2e%2e", "https://github.com/a/b#readme",
    "https://[invalid",
])
def test_rejects_non_repository_urls(value):
    with pytest.raises(RepositoryError):
        remote.normalize_github_url(value)


def local_transport(monkeypatch, demo_path):
    """Exercise actual Git cloning, fetching and cache logic with a local fixture."""
    calls = []

    def run(args, *, cwd=None, proxy=None):
        calls.append(list(args))
        translated = [Path(demo_path).as_uri() if x == "https://github.com/example/atlas.git" else x for x in args]
        # URL validation remains intact; only the network transport is substituted.
        result = subprocess.run(["git", *translated], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if result.returncode:
            raise RepositoryError("fixture transport failed: " + result.stderr)
        return result.stdout.strip()

    monkeypatch.setattr(remote, "_run_git", run)
    return calls


def test_actual_shallow_clone_cache_refresh_and_safe_diffs(monkeypatch, demo_path, snapshot, tmp_path):
    calls = local_transport(monkeypatch, demo_path)
    cache = tmp_path / "cache"
    info = remote.download_github("https://github.com/example/atlas", depth=6, cache_root=cache)
    assert info["name"] == "example/atlas"
    assert not info["download_cached"]
    assert not (Path(info["path"]) / "README.md").exists()  # no checkout
    assert Path(info["path"]).parent == cache
    assert not list(cache.glob("download-*"))
    spec = analysis_spec(info, info["current"], 100, False)
    assert spec["is_shallow"]
    assert spec["total_commits"] == 5  # six commits downloaded, one boundary excluded
    boundary = (Path(info["path"]) / ".git" / "shallow").read_text().strip()
    assert boundary not in spec["hashes"]
    raw_commit = git(info["path"], "cat-file", "-p", boundary)
    missing_parent = next(line.split()[1] for line in raw_commit.splitlines() if line.startswith("parent "))
    with pytest.raises(RepositoryError):
        git(info["path"], "cat-file", "-e", missing_parent)
    result = mine(spec)
    assert metrics(*frames(result))["commits"] == 5
    assert any("浅克隆" in warning for warning in result["meta"]["warnings"])
    # Every retained diff must equal the original full-history result.
    expected = {(c["commit_hash"], c["path"]): c for c in snapshot["changes"]}
    for change in result["changes"]:
        assert change == expected[change["commit_hash"], change["path"]]
    reused = remote.download_github("https://github.com/example/atlas.git", depth=6, cache_root=cache)
    assert reused["download_cached"]
    assert reused["path"] == info["path"]
    assert len(calls) == 1
    refreshed = remote.download_github("https://github.com/example/atlas", depth=6, refresh=True, cache_root=cache)
    assert refreshed["download_refreshed"]
    assert calls[-1][0] == "fetch"


def test_missing_shallow_parent_has_actionable_error(monkeypatch, demo_path, tmp_path):
    local_transport(monkeypatch, demo_path)
    info = remote.download_github("https://github.com/example/atlas", depth=6, cache_root=tmp_path)
    spec = analysis_spec(info, info["current"], 100, False)
    boundary = (Path(info["path"]) / ".git" / "shallow").read_text().strip()
    # An outdated caller including the boundary must expose the missing object,
    # rather than only a GitCommandError class name or an apparently valid scan.
    with pytest.raises(RepositoryError, match="浅克隆") as error:
        mine({**spec, "hashes": [boundary]})
    assert "bad object" in str(error.value)
    assert "读取文件差异" in str(error.value)


def test_downloads_requested_branch(monkeypatch, demo_path, tmp_path):
    local_transport(monkeypatch, demo_path)
    info = remote.download_github("https://github.com/example/atlas", branch="sprint-1", depth=20, cache_root=tmp_path)
    assert info["current"] == "refs/heads/sprint-1"
    assert git(info["path"], "rev-parse", "HEAD") == git(demo_path, "rev-parse", "sprint-1")
    assert analysis_spec(info, info["current"], 100, False)["total_commits"] == 9


def test_failed_clone_cleans_only_its_own_staging(monkeypatch, tmp_path):
    untouched = tmp_path / "my-existing-directory"
    untouched.mkdir()
    (untouched / "keep.txt").write_text("keep")

    def fail(args, **kwargs):
        clone = Path(args[-1])
        clone.mkdir()
        (clone / "partial").write_text("partial download")
        raise RepositoryError("simulated timeout")

    monkeypatch.setattr(remote, "_run_git", fail)
    with pytest.raises(RepositoryError, match="timeout"):
        remote.download_github("https://github.com/example/atlas", cache_root=tmp_path)
    assert list(tmp_path.iterdir()) == [untouched]
    assert (untouched / "keep.txt").read_text() == "keep"


def test_corrupted_cache_is_not_overwritten(monkeypatch, demo_path, tmp_path):
    local_transport(monkeypatch, demo_path)
    info = remote.download_github("https://github.com/example/atlas", depth=6, cache_root=tmp_path)
    marker = Path(info["path"]) / ".git" / "repolens-source.json"
    saved = json.loads(marker.read_text())
    saved["url"] = "https://github.com/someone/else.git"
    marker.write_text(json.dumps(saved))
    with pytest.raises(RepositoryError, match="来源不匹配"):
        remote.download_github("https://github.com/example/atlas", depth=6, cache_root=tmp_path)


def test_network_timeout_is_actionable_and_disables_login(monkeypatch):
    killed = []

    class Process:
        pid = 12345

        def __init__(self, args, **kwargs):
            assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
            assert kwargs["env"]["GCM_INTERACTIVE"] == "never"
            assert "credential.helper=" in args
            self.calls = 0

        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("git", timeout)
            return "", ""

        def poll(self):
            return None

        def kill(self):
            killed.append(self.pid)

    monkeypatch.setattr(remote.subprocess, "Popen", Process)
    monkeypatch.setattr(remote.subprocess, "run", lambda args, **kwargs: killed.append(args))
    if hasattr(remote.os, "killpg"):
        monkeypatch.setattr(remote.os, "killpg", lambda pid, sig: killed.append(pid))
    with pytest.raises(RepositoryError, match="下载超时"):
        remote._run_git(["clone", "https://github.com/example/atlas.git"])
    assert 12345 in killed


def test_git_connection_failure_has_specific_message(monkeypatch):
    class Process:
        returncode = 128

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return "", "fatal: Failed to connect to github.com port 443: Could not connect to server"

    monkeypatch.setattr(remote.subprocess, "Popen", Process)
    with pytest.raises(RepositoryError, match="Git 无法连接 GitHub"):
        remote._run_git(["clone", "https://github.com/example/atlas.git"])
