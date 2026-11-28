from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import os
import subprocess

import pytest

from repolens.completeness import CheckOptions, export_completeness, history_context, review_commit, score_candidates
from repolens.completeness_demo import create_completeness_demo
from repolens.mining import analysis_spec, git, inspect_repository, mine


@pytest.fixture(scope="module")
def completeness_snapshot(tmp_path_factory):
    path = create_completeness_demo(tmp_path_factory.mktemp("cochange") / "completeness_demo_repository")
    info = inspect_repository(path)
    return mine(analysis_spec(info, info["current"], 300, False))


def target_named(snapshot, phrase):
    return next(c["hash"] for c in snapshot["commits"] if phrase in c["message"])


def toy(history, target=("src/a.py",), existing=None):
    commits, changes = [], []
    for index, paths in enumerate([*history, target]):
        sha = f"{index:040x}"
        commits.append({"hash": sha, "is_merge": False, "message": "fixture", "committed_at": "2026-11-28T00:00:00+00:00"})
        for path in paths:
            changes.append({"commit_hash": sha, "path": path, "old_path": path, "new_path": path,
                            "change_type": "MODIFY", "diff": "@@ -1 +1 @@\n-old\n+new\n", "added_lines": 1, "deleted_lines": 1})
    snapshot = {"meta": {"id": "toy", "path": "fixture", "branch": "main", "tip": commits[-1]["hash"],
                          "hashes": [c["hash"] for c in commits], "total_commits": len(commits)},
                "commits": commits, "changes": changes}
    return snapshot, commits[-1]["hash"], [c["hash"] for c in commits[:-1]], existing or {path for paths in [*history, target] for path in paths}


def test_exact_association_and_duplicate_change_rows_do_not_inflate_counts():
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 3 + [("src/a.py",)])
    snapshot["changes"].append(dict(snapshot["changes"][0]))
    before = deepcopy(snapshot)
    result = score_candidates(snapshot, target, history, paths)
    assert result["status"] == "suggestions"
    assert result["candidates"][0]["path"] == "tests/test_a.py"
    rule = result["candidates"][0]["rules"][0]
    assert (rule["support"], rule["trigger_count"], rule["confidence"]) == (3, 4, 0.75)
    assert set(rule["evidence_hashes"]) == set(history[:3])
    assert snapshot == before
    assert score_candidates(snapshot, target, history, paths, CheckOptions(min_confidence=0.8))["status"] == "no_candidates"


def test_already_touched_aliases_and_nonexistent_candidates_excluded():
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 3, ("src/a.py", "tests/test_a.py"))
    assert not score_candidates(snapshot, target, history, paths)["candidates"]
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 3)
    assert not score_candidates(snapshot, target, history, {"src/a.py"})["candidates"]
    snapshot["changes"].append({"commit_hash": target, "path": "tests/renamed.py", "old_path": "tests/test_a.py",
                                "new_path": "tests/renamed.py", "change_type": "RENAME", "diff": "", "added_lines": 0, "deleted_lines": 0})
    assert not score_candidates(snapshot, target, history, paths | {"tests/renamed.py"})["candidates"]


def test_minimum_support_empty_history_and_zero_eligible_target():
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 2)
    assert score_candidates(snapshot, target, history, paths)["status"] == "insufficient_history"
    assert score_candidates(snapshot, target, [], paths)["status"] == "insufficient_history"
    snapshot["changes"][-1]["change_type"] = "ADD"
    assert score_candidates(snapshot, target, history, paths)["status"] == "no_eligible_files"
    with pytest.raises(ValueError, match="目标提交"):
        score_candidates(snapshot, "missing", history, paths)


def test_large_commits_locks_generated_and_binary_are_excluded():
    large = ("src/a.py", "tests/test_a.py", *[f"bulk/{i}.py" for i in range(22)])
    snapshot, target, history, paths = toy([large] * 3)
    result = score_candidates(snapshot, target, history, paths)
    assert result["skipped"]["large"] == 3 and not result["candidates"]
    ignored = ("src/a.py", "package-lock.json", "node_modules/pkg/a.js", "dist/app.js", "src/binary.dat")
    snapshot, target, history, paths = toy([ignored] * 3)
    for change in snapshot["changes"]:
        if change["path"].endswith("binary.dat"):
            change.update(diff="Binary files old and new differ", added_lines=0, deleted_lines=0)
    assert not score_candidates(snapshot, target, history, paths)["candidates"]
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 3, target=large)
    assert score_candidates(snapshot, target, history, paths)["status"] == "target_too_large"


def test_lifecycle_changes_in_history_invalidate_paths():
    snapshot, target, history, paths = toy([("src/a.py", "tests/test_a.py")] * 3 + [("tests/test_a.py",)])
    event = next(c for c in snapshot["changes"] if c["commit_hash"] == history[-1])
    event.update(change_type="DELETE", new_path=None)
    result = score_candidates(snapshot, target, history, paths)
    assert "tests/test_a.py" in result["unstable_paths"]
    assert not result["candidates"]


def test_merges_history_deduplication_multiple_triggers_and_top_k():
    snapshot, target, history, paths = toy([("src/a.py", "src/c.py", "tests/test_a.py", "docs/spec.md")] * 4, target=("src/a.py", "src/c.py"))
    snapshot["commits"][0]["is_merge"] = True
    result = score_candidates(snapshot, target, [*history, history[1], target, "unknown"], paths, CheckOptions(top_k=1))
    assert result["skipped"]["merge"] == 1
    assert result["candidate_count"] == 2 and len(result["candidates"]) == 1
    assert len(result["candidates"][0]["rules"]) == 2
    assert all(rule["support"] == 3 for rule in result["candidates"][0]["rules"])
    snapshot["commits"][-1]["is_merge"] = True
    assert score_candidates(snapshot, target, history, paths)["status"] == "unsupported_merge"


@pytest.mark.parametrize("options", [CheckOptions(min_support=1), CheckOptions(min_confidence=0), CheckOptions(min_confidence=float("nan")),
                                    CheckOptions(history_limit=0), CheckOptions(max_files=1), CheckOptions(top_k=0)])
def test_invalid_thresholds_rejected(options):
    with pytest.raises(ValueError):
        options.validate()


def test_real_git_demo_positive_complete_and_unrelated_controls(completeness_snapshot):
    snapshot = completeness_snapshot
    target = target_named(snapshot, "auth-only change")
    result = review_commit(snapshot, target)
    assert result["status"] == "suggestions"
    assert [item["path"] for item in result["candidates"]] == ["tests/test_auth.py"]
    assert result["candidates"][0]["rules"][0]["confidence"] == 1
    assert result["candidates"][0]["rules"][0]["support"] == 4
    assert result["baseline_paths"][0] == "src/cache.py"
    assert review_commit(snapshot, target_named(snapshot, "complete auth and test"))["status"] == "no_candidates"
    assert review_commit(snapshot, target_named(snapshot, "unrelated cache-only"))["status"] == "no_candidates"
    assert review_commit(snapshot, target, CheckOptions(history_limit=3))["status"] == "insufficient_history"
    assert target not in result["history_hashes"]
    assert target_named(snapshot, "complete auth and test") not in result["history_hashes"]


def test_git_tree_is_at_target_and_source_repository_unchanged(completeness_snapshot, tmp_path):
    original = completeness_snapshot["meta"]["path"]
    destination = tmp_path / "copy"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", original, str(destination)], check=True)
    git(destination, "rm", "tests/test_auth.py")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test", "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(destination), "commit", "-qm", "remove test after target"], check=True, env=env)
    info = inspect_repository(str(destination))
    snapshot = mine(analysis_spec(info, info["current"], 300, False))
    target = target_named(snapshot, "auth-only change")
    config = destination / ".git/config"
    before_config, before_head, before_status = config.read_bytes(), git(destination, "rev-parse", "HEAD"), git(destination, "status", "--porcelain")
    assert review_commit(snapshot, target)["candidates"][0]["path"] == "tests/test_auth.py"
    assert not (destination / "tests/test_auth.py").exists()
    assert (config.read_bytes(), git(destination, "rev-parse", "HEAD"), git(destination, "status", "--porcelain")) == (before_config, before_head, before_status)


def test_ancestry_excludes_sibling_branch_even_with_earlier_commit_dates(tmp_path):
    root = tmp_path / "branch-fixture"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "--initial-branch=main", str(root)], check=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.test", "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.test"}

    def commit(message, revision, paths, stamp):
        for name in paths:
            (root / name).write_text(f"VALUE = {revision}\n")
        git(root, "add", "--all")
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(root), "commit", "-qm", message],
                       check=True, env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})

    commit("root", 0, ["a.py", "b.py"], "2026-01-01T00:00:00+00:00")
    git(root, "checkout", "-b", "side")
    for index in range(1, 4):
        commit("side pair", index, ["a.py", "b.py"], f"2026-01-0{index + 1}T00:00:00+00:00")
    git(root, "checkout", "main")
    commit("target on main", 3, ["a.py"], "2026-01-10T00:00:00+00:00")
    target = git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(root), "merge", "--no-ff", "side", "-m", "merge side"], check=True, env=env, capture_output=True)
    info = inspect_repository(str(root))
    snapshot = mine(analysis_spec(info, info["current"], 300, False))
    result = review_commit(snapshot, target)
    assert result["status"] == "insufficient_history"
    assert len(result["history_hashes"]) == 1  # The common root; no side-branch pairs.


def test_clock_skew_does_not_remove_ancestor_evidence(completeness_snapshot):
    snapshot = deepcopy(completeness_snapshot)
    target = target_named(snapshot, "auth-only change")
    next(c for c in snapshot["commits"] if c["hash"] == target)["committed_at"] = "2000-01-01T00:00:00+00:00"
    assert review_commit(snapshot, target)["candidates"][0]["rules"][0]["support"] == 4


def test_report_is_traceable_escaped_and_explicit_about_limits():
    path = "tests/test|<a>.py"
    snapshot, target, history, paths = toy([("src/a.py", path)] * 3)
    snapshot["meta"]["is_shallow"] = True
    result = score_candidates(snapshot, target, history, paths)
    text = export_completeness(snapshot["meta"], result)
    assert "test&#124;&lt;a&gt;.py" in text
    assert "100.0%" in text and "3 条" in text
    assert "未调用 AI" in text and "不是缺陷概率" in text and "不证明变更完整" in text
    assert "浅克隆" in text and target in text and history[0] in text


def test_completeness_page_runs_and_invalidates_result_when_threshold_changes(completeness_snapshot):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["snapshot"] = completeness_snapshot
    app.run()
    assert not app.exception
    target = target_named(completeness_snapshot, "auth-only change")
    next(w for w in app.selectbox if w.label == "选择待检查提交").set_value(target).run()
    next(w for w in app.button if w.label == "检查潜在遗漏").click().run()
    assert not app.exception
    assert any("潜在遗漏检查建议" in item.value for item in app.warning)
    table = next(item.value for item in app.dataframe if "建议检查文件" in item.value)
    assert table.iloc[0]["建议检查文件"] == "tests/test_auth.py"
    next(w for w in app.number_input if w.label == "最少共同修改次数").set_value(5).run()
    assert not app.exception
    assert not any("潜在遗漏检查建议" in item.value for item in app.warning)
    next(w for w in app.button if w.label == "检查潜在遗漏").click().run()
    assert not app.exception
    assert any("历史证据不足" in item.value for item in app.info)


def test_masked_replay_has_no_target_leakage_and_reports_baseline(completeness_snapshot):
    from repolens.completeness_eval import evaluate_masked_replay

    target = target_named(completeness_snapshot, "complete auth and test")
    before = deepcopy(completeness_snapshot)
    result = evaluate_masked_replay(completeness_snapshot, CheckOptions(top_k=5), target_hashes=[target], all_files=True)
    assert result["case_count"] == 2
    assert result["rules"]["hit_at_1"] == 2
    assert result["frequency_baseline"]["hit_at_1"] == 0
    assert result["frequency_baseline"]["hit_at_k"] == 2
    assert all(case["hidden_path"] in case["suggestions"] for case in result["cases"])
    assert completeness_snapshot == before
    # Empty and cold-start cases retain their actual denominator and abstentions.
    empty = evaluate_masked_replay(completeness_snapshot, target_hashes=[])
    assert empty["case_count"] == 0 and empty["rules"]["recovery_at_k"] is None
    earliest = next(c["hash"] for c in completeness_snapshot["commits"] if "together 1" in c["message"])
    cold = evaluate_masked_replay(completeness_snapshot, target_hashes=[earliest])
    assert cold["case_count"] == 1 and cold["abstained_cases"] == 1
    assert cold["rules"]["recovery_at_k"] == 0
