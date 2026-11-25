from datetime import date

import pytest

from repolens.analytics import filter_frames, frames
from repolens.reports import export_markdown, factual_report
from repolens.sprints import coverage_note, repository_key
from repolens.storage import delete_sprint, list_sprints, save_sprint


def test_sprint_persistence_update_duplicate_and_repository_isolation(tmp_path):
    db = tmp_path / "sprints.sqlite3"
    first = save_sprint("repo-a", "Sprint 1", "2026-11-09", "2026-11-14", db)
    second = save_sprint("repo-a", "Sprint 2", "2026-11-15", "2026-11-22", db)
    assert len(list_sprints("repo-a", db)) == 2
    assert list_sprints("repo-b", db) == []
    with pytest.raises(ValueError, match="同名"):
        save_sprint("repo-a", "Sprint 1", "2026-11-09", "2026-11-14", db)
    save_sprint("repo-a", "Sprint One", "2026-11-10", "2026-11-14", db, sprint_id=first)
    assert list_sprints("repo-a", db)[0]["start"] == "2026-11-10"
    delete_sprint("repo-b", first, db)
    assert len(list_sprints("repo-a", db)) == 2
    delete_sprint("repo-a", second, db)
    assert len(list_sprints("repo-a", db)) == 1


@pytest.mark.parametrize("name,start,end", [("", "2026-11-09", "2026-11-14"), ("Sprint", "2026-11-14", "2026-11-09")])
def test_invalid_sprints_rejected(tmp_path, name, start, end):
    with pytest.raises(ValueError):
        save_sprint("repo", name, start, end, tmp_path / "db.sqlite3")


def test_sprint_reports_use_exact_range_and_method_details(snapshot):
    commits, changes = frames(snapshot)
    sprint = {"id": "one", "name": "Sprint 1", "start": "2026-11-09", "end": "2026-11-14"}
    selected, files = filter_frames(commits, changes, date(2026, 11, 9), date(2026, 11, 14))
    assert len(selected) == 9
    context = {"title": "Sprint 1 变化报告", "start": sprint["start"], "end": sprint["end"], "timezone": "Asia/Shanghai", "authors": [], "modules": [], "sprint": sprint}
    report = export_markdown(snapshot["meta"], context, selected, files, factual_report(selected, files))
    assert "Sprint：Sprint 1" in report
    assert "提交 9" in report
    assert "Changed methods" in report
    assert "read_metadata" in report
    assert "src/reports/export.py" not in report
    assert coverage_note(snapshot["meta"], commits, date(2026, 11, 1), date(2026, 11, 14))


def test_remote_sprints_survive_cache_depth_and_snapshot_changes():
    assert repository_key({"source_url": "https://github.com/Org/Repo", "path": "/cache/a"}) == repository_key({"source_url": "https://github.com/org/repo.git", "path": "/cache/b"})
