from datetime import date
from pathlib import Path

import pytest

from repolens.analytics import daily_activity, developer_activity, file_activity, filter_frames, frames, metrics
from repolens.mining import RepositoryError, analysis_spec, git, inspect_repository, mine
from repolens.reports import build_ai_payload, export_markdown, factual_report
from repolens.storage import load_snapshot, load_summary, save_snapshot, save_summary


def test_extract_rename_delete_and_exact_totals(snapshot):
    commits, changes = frames(snapshot)
    assert metrics(commits, changes) == {"commits": 18, "developers": 3, "files": 14, "added": 62, "deleted": 8, "merges": 0}
    rename = changes[changes["change_type"] == "RENAME"].iloc[0]
    assert rename["old_path"] == "src/mining/reader.py"
    assert rename["new_path"] == "src/mining/extractor.py"
    deletion = changes[changes["change_type"] == "DELETE"].iloc[0]
    assert deletion["new_path"] is None
    assert deletion["path"] == "tests/test_reader.py"


def test_mining_is_read_only_and_limit_is_explicit(demo_path):
    config = Path(demo_path) / ".git" / "config"
    before = config.read_bytes()
    head = git(demo_path, "rev-parse", "HEAD")
    info = inspect_repository(demo_path)
    spec = analysis_spec(info, "refs/heads/sprint-1", 4, False)
    scanned = mine(spec)
    assert len(scanned["commits"]) == 4
    assert scanned["meta"]["total_commits"] == 9
    assert scanned["meta"]["tip"] == git(demo_path, "rev-parse", "sprint-1")
    assert any("非完整历史" in w for w in scanned["meta"]["warnings"])
    assert config.read_bytes() == before
    assert git(demo_path, "rev-parse", "HEAD") == head
    assert git(demo_path, "status", "--porcelain") == ""


def test_shared_filter_and_developer_aggregation(snapshot):
    commits, changes = frames(snapshot)
    selected, files = filter_frames(commits, changes, date(2026, 11, 10), date(2026, 11, 16), ["bob@example.test"], ["src"])
    assert len(selected) == 4
    assert set(files["module"]) == {"src"}
    assert set(files["commit_hash"]) == set(selected["hash"])
    assert developer_activity(selected, files).iloc[0]["commits"] == 4
    assert file_activity(files).iloc[0]["path"] == "src/ui/dashboard.py"


def test_zero_result_and_zero_days(snapshot):
    commits, changes = frames(snapshot)
    selected, files = filter_frames(commits, changes, date(2026, 11, 9), date(2026, 11, 22), ["nobody@example.test"])
    assert metrics(selected, files)["commits"] == 0
    assert daily_activity(selected, files).empty
    daily = daily_activity(commits, changes)
    assert len(daily) == 14
    assert daily["commits"].sum() == 18


def test_timezone_controls_date_boundary(snapshot):
    custom = {"commits": [{**snapshot["commits"][0], "committed_at": "2026-11-09T20:00:00+00:00"}], "changes": []}
    shanghai, _ = frames(custom, "Asia/Shanghai")
    utc, _ = frames(custom, "UTC")
    assert shanghai.iloc[0]["date"] == date(2026, 11, 10)
    assert utc.iloc[0]["date"] == date(2026, 11, 9)


def test_database_round_trip_and_report_scope(snapshot, tmp_path):
    db = tmp_path / "cache.sqlite3"
    save_snapshot(snapshot, db)
    assert load_snapshot(snapshot["meta"]["id"], db) == snapshot
    assert load_snapshot("missing", db) is None
    commits, changes = frames(snapshot)
    commits, changes = filter_frames(commits, changes, date(2026, 11, 19), date(2026, 11, 22), modules=["docs"])
    report = factual_report(commits, changes)
    context = {"title": "Sprint 2", "start": "2026-11-19", "end": "2026-11-22", "timezone": "Asia/Shanghai", "authors": [], "modules": ["docs"]}
    markdown = export_markdown(snapshot["meta"], context, commits, changes, report)
    assert "提交 2" in markdown
    assert "统计报告（未调用 AI）" in markdown
    assert "docs/sprint-review.md" in markdown
    assert "src/ui/dashboard.py" not in markdown
    save_summary("scope-1", report, db)
    assert load_summary("scope-1", db) == report


def test_invalid_and_empty_repositories(tmp_path):
    with pytest.raises(RepositoryError):
        inspect_repository(str(tmp_path / "missing"))
    git(tmp_path, "init", "--initial-branch=main")
    with pytest.raises(RepositoryError, match="没有提交"):
        inspect_repository(str(tmp_path))


def test_ai_payload_budget_and_sampling(snapshot):
    commits, changes = frames(snapshot)
    commits = commits.iloc[[0]].copy()
    all_commits, all_changes = [], []
    for index in range(80):
        c = commits.copy()
        c["hash"] = f"{index:040x}"
        f = changes.head(10).copy()
        f["commit_hash"] = f"{index:040x}"
        f["diff"] = "+line\n" * 5000
        all_commits.append(c)
        all_changes.append(f)
    import pandas as pd
    payload = build_ai_payload(pd.concat(all_commits), pd.concat(all_changes))
    assert payload["coverage"]["selected_commits"] == 80
    assert payload["coverage"]["evidence_commits"] == 40
    assert sum(len(f["diff"]) for c in payload["commits"] for f in c["files"]) <= 48_000
    assert any(f["diff_truncated"] for c in payload["commits"] for f in c["files"])


def test_merge_binary_empty_commit_and_dirty_workspace(tmp_path):
    def command(*args):
        return git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "-c", "commit.gpgsign=false", *args)

    command("init", "--initial-branch=main")
    (tmp_path / "asset.bin").write_bytes(b"\x00\x01\x02\x03" * 100)
    command("add", "--all")
    command("commit", "-m", "add binary asset")
    command("checkout", "-b", "feature")
    (tmp_path / "feature.txt").write_text("feature\n")
    command("add", "--all")
    command("commit", "-m", "feature")
    command("checkout", "main")
    (tmp_path / "main.txt").write_text("main\n")
    command("add", "--all")
    command("commit", "-m", "main")
    command("merge", "--no-ff", "feature", "-m", "merge feature")
    command("commit", "--allow-empty", "-m", "empty commit")
    (tmp_path / "main.txt").write_text("uncommitted edit\n")
    (tmp_path / "untracked.txt").write_text("do not touch\n")
    status = command("status", "--porcelain")
    config = (tmp_path / ".git" / "config").read_bytes()
    info = inspect_repository(str(tmp_path))
    result = mine(analysis_spec(info, info["current"], 100, True))
    commits, changes = frames(result)
    assert len(commits) == 5
    assert metrics(commits, changes)["merges"] == 1
    assert not changes[changes["path"] == "asset.bin"].empty
    assert "untracked.txt" not in changes["path"].tolist()
    assert not changes["diff"].str.contains("uncommitted edit").any()
    merge_hash = commits.loc[commits["is_merge"], "hash"].iloc[0]
    assert changes[changes["commit_hash"] == merge_hash].empty
    assert (tmp_path / ".git" / "config").read_bytes() == config
    assert command("status", "--porcelain") == status
    without_merges = analysis_spec(info, info["current"], 100, False)
    assert without_merges["total_commits"] == 4
