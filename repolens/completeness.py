"""Bounded, explainable suggestions from earlier co-modification history.

Rules are A -> B with support count count(A,B) and association rate
count(A,B)/count(A), learned from eligible ancestor commits only. These are
review suggestions, not probabilities of defects or proofs of completeness.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import math
from pathlib import PurePosixPath
import subprocess

from repolens.mining import RepositoryError, git


DETECTOR_VERSION = "cochange-v1"
EVIDENCE_LIMIT = 5
IGNORED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "vendor", "dist", "build", "__pycache__"}
IGNORED_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
                 "pipfile.lock", "cargo.lock", "composer.lock", "gemfile.lock", "requirements.lock"}


@dataclass(frozen=True)
class CheckOptions:
    history_limit: int = 500
    min_support: int = 3
    min_confidence: float = 0.6
    max_files: int = 20
    top_k: int = 20

    def validate(self):
        for name, low, high in (("history_limit", 1, 2000), ("min_support", 2, 100),
                                ("max_files", 2, 100), ("top_k", 1, 50)):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise ValueError(f"{name} 必须是 {low}–{high} 的整数。")
        if not isinstance(self.min_confidence, (int, float)) or not math.isfinite(self.min_confidence) or not 0 < self.min_confidence <= 1:
            raise ValueError("历史关联比例必须大于 0 且不超过 1。")


def allowed_path(path):
    pieces = PurePosixPath(path).parts
    return bool(pieces) and not any(part.lower() in IGNORED_DIRECTORIES for part in pieces) and pieces[-1].lower() not in IGNORED_NAMES and not pieces[-1].lower().endswith((".min.js", ".map"))


def text_modification(change):
    diff = change.get("diff") or ""
    return (change.get("change_type") == "MODIFY" and allowed_path(change["path"])
            and bool(diff) and "GIT binary patch" not in diff and not diff.startswith("Binary files ")
            and change.get("added_lines", 0) + change.get("deleted_lines", 0) > 0)


def touched_paths(changes):
    return {path for change in changes for path in (change.get("old_path"), change.get("new_path"), change.get("path")) if path}


def history_context(snapshot, target_hash, options):
    """Read Git ancestry and the target's tree without checking out anything."""
    options.validate()
    target = next((c for c in snapshot["commits"] if c["hash"] == target_hash), None)
    if target is None:
        raise ValueError("目标提交不在当前已采集快照中。")
    if target["is_merge"]:
        return [], set()
    path = snapshot["meta"]["path"]
    parents = git(path, "rev-list", "--parents", "-n", "1", target_hash).split()[1:]
    ancestors = git(path, "rev-list", "--topo-order", "--no-merges", "--max-count=2000", *parents).splitlines() if parents else []
    known = {c["hash"] for c in snapshot["commits"]}
    history = [sha for sha in ancestors if sha in known and sha != target_hash][:options.history_limit]
    try:
        tree = subprocess.run(["git", "-C", path, "ls-tree", "-r", "-z", target_hash],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RepositoryError("无法读取目标提交的文件树，请确认本地 Git 仓库仍可访问。") from exc
    if tree.returncode:
        raise RepositoryError("无法读取目标提交的文件树；请重新采集仓库后再检查。")
    existing = set()
    for item in tree.stdout.split("\0"):
        if "\t" in item:
            metadata, filename = item.split("\t", 1)
            if metadata.split()[1] == "blob":
                existing.add(filename)
    return history, existing


def score_candidates(snapshot, target_hash, history_hashes, existing_paths, options=CheckOptions()):
    """Pure scoring; callers supply validated ancestor hashes and a target tree."""
    options.validate()
    commits = {c["hash"]: c for c in snapshot["commits"]}
    if target_hash not in commits:
        raise ValueError("目标提交不在当前已采集快照中。")
    grouped = defaultdict(list)
    for change in snapshot["changes"]:
        grouped[change["commit_hash"]].append(change)
    current_changes = grouped[target_hash]
    current_paths = touched_paths(current_changes)
    history = list(dict.fromkeys(sha for sha in history_hashes if sha in commits and sha != target_hash))[:options.history_limit]
    result = {
        "detector_version": DETECTOR_VERSION, "snapshot_id": snapshot["meta"]["id"],
        "target": dict(commits[target_hash]), "options": asdict(options),
        "target_paths": sorted(current_paths), "seeds": [], "seed_counts": {},
        "history_hashes": history, "history_considered": len(history), "history_used": 0,
        "skipped": {"merge": 0, "large": 0, "no_text_modifications": 0},
        "unstable_paths": [], "candidates": [], "candidate_count": 0, "baseline_paths": [],
        "status": "no_candidates", "warnings": [],
    }
    meta = snapshot["meta"]
    if meta.get("is_shallow") or len(meta.get("hashes", commits)) < meta.get("total_commits", len(commits)):
        result["warnings"].append("本次历史为浅克隆或采集子集；规则只代表其中已采集的祖先提交。")
    if commits[target_hash]["is_merge"]:
        result["status"] = "unsupported_merge"
        return result
    if len(current_paths) > options.max_files:
        result["status"] = "target_too_large"
        return result
    # Avoid treating a renamed/deleted path as a stable identity across the window.
    unstable = touched_paths([change for sha in history for change in grouped[sha]
                              if change["change_type"] in {"DELETE", "RENAME"}])
    result["unstable_paths"] = sorted(unstable)
    seeds = {c["path"] for c in current_changes if text_modification(c) and c["path"] not in unstable}
    result["seeds"] = sorted(seeds)
    if not seeds:
        result["status"] = "no_eligible_files"
        return result
    frequencies, seed_counts, pair_counts = Counter(), Counter(), Counter()
    evidence = defaultdict(list)
    for sha in history:
        if commits[sha]["is_merge"]:
            result["skipped"]["merge"] += 1
            continue
        changes = grouped[sha]
        if len(touched_paths(changes)) > options.max_files:
            result["skipped"]["large"] += 1
            continue
        paths = {c["path"] for c in changes if text_modification(c) and c["path"] not in unstable}
        if not paths:
            result["skipped"]["no_text_modifications"] += 1
            continue
        result["history_used"] += 1
        frequencies.update(paths)
        for seed in seeds & paths:
            seed_counts[seed] += 1
            for candidate in paths - current_paths:
                if candidate not in existing_paths:
                    continue
                pair = (seed, candidate)
                pair_counts[pair] += 1
                if len(evidence[pair]) < EVIDENCE_LIMIT:
                    evidence[pair].append(sha)
    result["seed_counts"] = {seed: seed_counts[seed] for seed in sorted(seeds)}
    by_candidate = defaultdict(list)
    for (seed, candidate), support in pair_counts.items():
        confidence = support / seed_counts[seed]
        if support >= options.min_support and confidence >= options.min_confidence:
            by_candidate[candidate].append({"trigger": seed, "support": support,
                                            "trigger_count": seed_counts[seed], "confidence": confidence,
                                            "evidence_hashes": evidence[(seed, candidate)]})
    for candidate, rules in by_candidate.items():
        rules.sort(key=lambda rule: (-rule["confidence"], -rule["support"], rule["trigger"]))
        result["candidates"].append({"path": candidate, "rules": rules})
    result["candidates"].sort(key=lambda item: (-item["rules"][0]["confidence"], -item["rules"][0]["support"], item["path"]))
    result["candidate_count"] = len(result["candidates"])
    result["candidates"] = result["candidates"][:options.top_k]
    result["baseline_paths"] = [path for path, count in sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
                                if path not in current_paths and path in existing_paths][:options.top_k]
    result["status"] = "suggestions" if result["candidates"] else "insufficient_history" if not seed_counts or max(seed_counts.values()) < options.min_support else "no_candidates"
    return result


def review_commit(snapshot, target_hash, options=CheckOptions()):
    history, existing = history_context(snapshot, target_hash, options)
    return score_candidates(snapshot, target_hash, history, existing, options)


STATUS_TEXT = {
    "suggestions": "发现建议人工检查的关联文件。",
    "no_candidates": "当前历史窗口与阈值下未发现候选文件；这不代表该提交已经完整。",
    "insufficient_history": "历史证据不足，暂时不能形成可靠的关联建议。",
    "no_eligible_files": "目标提交没有可用的稳定文本修改路径；新增、删除、重命名和二进制不作为触发文件。",
    "unsupported_merge": "当前检测不支持 merge 提交，请选择普通提交。",
    "target_too_large": "目标提交涉及路径过多，超出当前小规模变更检查范围。",
}


def _plain(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\r", " ").replace("\n", " ").replace("`", "'")


def export_completeness(meta, result):
    opts, target = result["options"], result["target"]
    lines = ["# ChangeGuard 潜在遗漏修改检查", "", "基于历史共同修改规则的人工检查建议；未调用 AI。", "",
             f"- 仓库：{_plain(meta.get('source_url') or meta['path'])}",
             f"- 分支：{_plain(meta['branch'])}；tip：{meta['tip']}",
             f"- 快照：{result['snapshot_id']}；检测器：{result['detector_version']}",
             f"- 目标提交：{target['hash']}", f"- 提交说明：{_plain(target['message'])}",
             f"- 历史：窗口上限 {opts['history_limit']}，已采集祖先 {result['history_considered']}，有效事务 {result['history_used']}",
             f"- 阈值：共同修改至少 {opts['min_support']} 次；关联比例至少 {opts['min_confidence']:.0%}；每提交最多 {opts['max_files']} 个路径",
             "", "## 检查结果", "", STATUS_TEXT[result["status"]], "", "## 当前提交触及的路径", "",
             *("- " + _plain(path) for path in result["target_paths"]), "", "## 候选与解释", ""]
    for candidate in result["candidates"]:
        lines += ["### 建议检查 " + _plain(candidate["path"]), ""]
        for rule in candidate["rules"]:
            lines += [f"- 触发文件：{_plain(rule['trigger'])}。历史中修改它的 {rule['trigger_count']} 条有效提交里，"
                      f"有 {rule['support']} 条也修改了该候选，关联比例 {rule['confidence']:.1%}。",
                      f"- 共同修改依据（最多 {EVIDENCE_LIMIT} 条）：" + ", ".join(rule["evidence_hashes"])]
        lines.append("")
    if result["candidate_count"] > len(result["candidates"]):
        lines.append(f"共 {result['candidate_count']} 个候选，仅展示前 {len(result['candidates'])} 个。")
    lines += ["", "## 范围与口径", "",
              "- 只使用目标提交的祖先，并与当前快照已采集提交取交集；不使用目标本身、后续提交或同级分支。",
              "- 历史窗口独立于页面日期、作者及模块筛选；当前提交使用完整路径列表。",
              "- 仅学习 MODIFY 文本变更；跳过 merge、大规模提交、锁文件、生成目录和窗口内重命名/删除过的路径。",
              "- 候选必须存在于目标提交的文件树，且没有被该提交触及。",
              "- 关联比例 = 共同修改次数 / 触发文件的修改次数，分母限于有效历史事务；不是缺陷概率。",
              "- 文件级历史相关性不能证明业务上必须一起修改；可能误报或漏报，未提示也不证明变更完整。",
              f"- 跳过事务：{result['skipped']}；窗口内不稳定路径：{len(result['unstable_paths'])} 个。",
              *("- " + _plain(note) for note in result["warnings"]) ]
    return "\n".join(lines) + "\n"
