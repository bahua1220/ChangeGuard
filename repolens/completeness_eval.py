"""Time-ordered masked-change replay, not a real-defect accuracy estimate."""

from repolens.completeness import CheckOptions, history_context, score_candidates, text_modification, touched_paths


def evaluate_masked_replay(snapshot, options=CheckOptions(top_k=5), max_cases=20, target_hashes=None, all_files=False):
    options.validate()
    if not 1 <= max_cases <= 100:
        raise ValueError("评估案例上限需为 1–100。")
    known = {c["hash"]: c for c in snapshot["commits"]}
    selected = target_hashes if target_hashes is not None else [c["hash"] for c in snapshot["commits"]]
    cases = []
    for target in selected:
        if target not in known or known[target]["is_merge"]:
            continue
        changes = [c for c in snapshot["changes"] if c["commit_hash"] == target]
        eligible = sorted({c["path"] for c in changes if text_modification(c)})
        if len(eligible) < 2 or len(touched_paths(changes)) > options.max_files:
            continue
        history, existing = history_context(snapshot, target, options)
        for hidden in eligible if all_files else eligible[-1:]:
            masked = {**snapshot, "changes": [c for c in snapshot["changes"] if not (c["commit_hash"] == target and c["path"] == hidden)]}
            result = score_candidates(masked, target, history, existing, options)
            predicted = [item["path"] for item in result["candidates"]]
            baseline = result["baseline_paths"]

            def rank(paths):
                return paths.index(hidden) + 1 if hidden in paths else None

            cases.append({"target": target, "hidden_path": hidden, "status": result["status"],
                          "history_used": result["history_used"], "suggestions": predicted, "frequency_baseline": baseline,
                          "rank": rank(predicted), "baseline_rank": rank(baseline)})
            if len(cases) >= max_cases:
                break
        if len(cases) >= max_cases:
            break
    total = len(cases)

    def summary(field):
        ranks = [case[field] for case in cases]
        return {"hit_at_1": sum(value == 1 for value in ranks), "hit_at_k": sum(value is not None for value in ranks),
                "recovery_at_k": sum(value is not None for value in ranks) / total if total else None,
                "mean_reciprocal_rank": sum(1 / value for value in ranks if value) / total if total else None}

    return {"mode": "masked_change_replay", "snapshot_id": snapshot["meta"]["id"], "top_k": options.top_k,
            "case_count": total, "abstained_cases": sum(not case["suggestions"] for case in cases),
            "rules": summary("rank"), "frequency_baseline": summary("baseline_rank"), "cases": cases,
            "limitations": ["人工遮蔽本来已修改的文件，仅衡量候选找回能力，不是实际遗漏或缺陷的正确率。",
                            "每个案例只用目标的已采集祖先，遮蔽文件不进入目标触及列表。",
                            "频率基线与规则使用相同有效历史、路径排除和候选存在性条件。",
                            "有限历史、规则阈值及案例选择都会影响结果；空建议也计入评估分母。"]}
