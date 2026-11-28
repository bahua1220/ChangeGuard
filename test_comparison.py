from datetime import date

import pandas as pd
import pytest

from repolens.analytics import frames
from repolens.comparison import compare_sprints, export_comparison, metric_table


SPRINT_A = {"id": "one", "name": "Sprint 1", "start": "2026-11-09", "end": "2026-11-14"}
SPRINT_B = {"id": "two", "name": "Sprint 2", "start": "2026-11-15", "end": "2026-11-22"}


def compare(snapshot, a=SPRINT_A, b=SPRINT_B, **filters):
    commits, changes = frames(snapshot)
    return compare_sprints(snapshot["meta"], commits, changes, a, b, **filters)


def test_exact_totals_duration_and_path_union(snapshot):
    result = compare(snapshot)
    assert result["a"]["stats"] == {
        "commits": 9, "developers": 3, "files": 8, "added": 38, "deleted": 1,
        "merges": 0, "days": 6, "churn": 39, "commits_per_day": 1.5,
    }
    assert result["b"]["stats"] == {
        "commits": 9, "developers": 3, "files": 10, "added": 24, "deleted": 7,
        "merges": 0, "days": 8, "churn": 31, "commits_per_day": 1.125,
    }
    assert any("时长不同" in note for note in result["warnings"])
    indexed = result["metrics"].set_index("metric")
    assert indexed.loc["新增行", "delta"] == -14
    assert indexed.loc["新增行", "percent"] == pytest.approx(-14 / 38 * 100)
    assert len(result["files"]) == 14
    files = result["files"].set_index("path")
    assert files.loc["src/mining/reader.py", "scope"] == "仅 A 有变更"
    assert files.loc["src/mining/extractor.py", "scope"] == "仅 B 有变更"
    # Pure rename has one touching commit even with zero churn.
    assert files.loc["src/mining/extractor.py", "commits_b"] == 1
    assert files.loc["src/mining/extractor.py", "churn_b"] == 0
    assert files.loc["tests/test_reader.py", "scope"] == "两期均有变更"
    assert result["modules"].set_index("module").loc["src", "churn_delta"] == -10


def test_same_filters_applied_independently_and_no_input_mutation(snapshot):
    commits, changes = frames(snapshot)
    original_commits, original_changes = commits.copy(deep=True), changes.copy(deep=True)
    result = compare_sprints(snapshot["meta"], commits, changes, SPRINT_A, SPRINT_B,
                             authors=["bob@example.test"], modules=["src"])
    assert result["a"]["stats"]["commits"] == 3
    assert result["b"]["stats"]["commits"] == 2
    for label in ("a", "b"):
        assert set(result[label]["commits"]["author_id"]) == {"bob@example.test"}
        assert set(result[label]["changes"]["module"]) == {"src"}
    pd.testing.assert_frame_equal(commits, original_commits)
    pd.testing.assert_frame_equal(changes, original_changes)


def test_zero_baseline_and_both_empty_are_defined_without_infinity(snapshot):
    empty = {**SPRINT_A, "start": "2026-01-01", "end": "2026-01-01"}
    result = compare(snapshot, a=empty)
    assert result["a"]["stats"]["commits"] == 0
    assert pd.isna(result["metrics"].set_index("metric").loc["提交数", "percent"])
    assert metric_table(result).set_index("指标").loc["提交数", "变化率"] == "—（A 为 0）"
    assert result["files"]["scope"].eq("仅 B 有变更").all()
    assert any("不能据此断言" in note for note in result["warnings"])
    both = compare(snapshot, authors=["nobody@example.test"])
    assert both["files"].empty and both["modules"].empty
    assert "nan" not in export_comparison(snapshot["meta"], both, "Asia/Shanghai").lower()


def test_overlapping_inclusive_dates_and_reverse_direction(snapshot):
    overlapping = {**SPRINT_B, "start": SPRINT_A["end"]}
    result = compare(snapshot, b=overlapping)
    assert any("范围重叠" in note for note in result["warnings"])
    shared = set(result["a"]["commits"]["hash"]) & set(result["b"]["commits"]["hash"])
    assert len(shared) == 1  # Nov 14 belongs to both inclusive ranges.
    reverse = compare(snapshot, a=SPRINT_B, b=SPRINT_A)
    assert reverse["metrics"].set_index("metric").loc["新增行", "delta"] == 14
    with pytest.raises(ValueError, match="开始日期"):
        compare(snapshot, a={**SPRINT_A, "start": "2026-12-01"})


def test_export_scope_limits_and_markdown_escaping(snapshot):
    partial = {**snapshot, "meta": {**snapshot["meta"], "is_shallow": True}}
    result = compare(partial, a={**SPRINT_A, "name": "First | <script>\nSprint"}, modules=["src"])
    report = export_comparison(partial["meta"], result, "Asia/Shanghai")
    assert "First &#124; &lt;script&gt; Sprint" in report
    assert "未调用 AI" in report and "历史不完整" in report
    assert snapshot["meta"]["id"] in report and snapshot["meta"]["tip"] in report
    assert "模块筛选：src" in report and "日期依据：committer date" in report
    assert "仅 A/B 有变更不代表文件新增或删除" in report
    assert "tests/test_reader.py" not in report
    assert "src/reports/export.py" in report


def test_timezone_boundary_is_used_in_both_ranges(snapshot):
    custom = {**snapshot, "commits": [{**snapshot["commits"][0], "committed_at": "2026-11-09T20:00:00+00:00"}], "changes": []}
    a = {**SPRINT_A, "start": "2026-11-09", "end": "2026-11-09"}
    b = {**SPRINT_B, "start": "2026-11-10", "end": "2026-11-10"}
    c, f = frames(custom, "Asia/Shanghai")
    local = compare_sprints(custom["meta"], c, f, a, b)
    c, f = frames(custom, "UTC")
    utc = compare_sprints(custom["meta"], c, f, a, b)
    assert (local["a"]["stats"]["commits"], local["b"]["stats"]["commits"]) == (0, 1)
    assert (utc["a"]["stats"]["commits"], utc["b"]["stats"]["commits"]) == (1, 0)


def test_export_file_limit_is_explicit(snapshot):
    result = compare(snapshot)
    rows = [dict(result["files"].iloc[0], path=f"generated/file-{i}.py") for i in range(101)]
    result["files"] = pd.DataFrame(rows)
    report = export_comparison(snapshot["meta"], result, "Asia/Shanghai")
    assert "100 / 101" in report
    assert "generated/file-99.py" in report
    assert "generated/file-100.py" not in report


@pytest.mark.parametrize("sprint_count", [0, 1, 2])
def test_comparison_view_handles_saved_range_count(monkeypatch, snapshot, sprint_count):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from repolens import storage

    monkeypatch.setattr(storage, "list_sprints", lambda *args: [SPRINT_A, SPRINT_B][:sprint_count])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["snapshot"] = snapshot
    app.run()
    assert not app.exception
    if sprint_count < 2:
        assert any("创建至少两个" in item.value for item in app.info)
    else:
        assert next(item for item in app.selectbox if item.label == "对比 Sprint A").value == "one"
        assert next(item for item in app.selectbox if item.label == "对比 Sprint B").value == "two"
        # The independently selected comparison survives an empty main range.
        next(item for item in app.date_input if item.label == "日期范围（含首尾）").set_value((date(2026, 1, 1), date(2026, 1, 2))).run()
        assert not app.exception
        assert any("仍可使用 Sprint 对比" in item.value for item in app.info)
        tables = [item.value for item in app.dataframe]
        metrics = next(table for table in tables if "指标" in table)
        assert metrics.set_index("指标").loc["提交数", "A"] == "9"
        next(item for item in app.selectbox if item.label == "对比 Sprint B").set_value("one").run()
        assert not app.exception
        assert any("两个不同" in item.value for item in app.info)
        # Editing/deleting a saved definition must not leave a stale selection.
        monkeypatch.setattr(storage, "list_sprints", lambda *args: [SPRINT_B, {**SPRINT_A, "id": "new"}])
        app.run()
        assert not app.exception
        assert next(item for item in app.selectbox if item.label == "对比 Sprint A").value == "two"
