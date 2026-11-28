"""Reproducible local evaluation: synthetic controls or a mined local repo."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repolens.completeness import CheckOptions, export_completeness, review_commit
from repolens.completeness_demo import create_completeness_demo
from repolens.completeness_eval import evaluate_masked_replay
from repolens.mining import analysis_spec, inspect_repository, mine


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--repository")
    parser.add_argument("--branch")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--cases", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "work/completeness-evaluation")
    args = parser.parse_args()
    info = inspect_repository(create_completeness_demo() if args.demo else args.repository)
    snapshot = mine(analysis_spec(info, args.branch or info["current"], args.limit, False))
    options = CheckOptions(top_k=args.top_k)
    controls = []
    targets = None
    args.output.mkdir(parents=True, exist_ok=True)
    if args.demo:
        for phrase, expected in (("auth-only change", ["tests/test_auth.py"]), ("complete auth and test", []), ("unrelated cache-only", [])):
            target = next(c for c in snapshot["commits"] if phrase in c["message"])
            result = review_commit(snapshot, target["hash"], options)
            observed = [c["path"] for c in result["candidates"]]
            controls.append({"scenario": phrase, "expected": expected, "observed": observed, "passed": observed == expected})
            if phrase == "auth-only change":
                (args.output / "example-completeness-report.md").write_text(export_completeness(snapshot["meta"], result), encoding="utf-8")
        targets = [next(c["hash"] for c in snapshot["commits"] if "complete auth and test" in c["message"])]
    evaluation = evaluate_masked_replay(snapshot, options, args.cases, targets, all_files=args.demo)
    evaluation.update({"source": "synthetic_demo" if args.demo else "local_repository", "repository": info["path"],
                       "branch": snapshot["meta"]["branch"], "tip": snapshot["meta"]["tip"], "options": options.__dict__,
                       "case_selection": "完整控制提交分别遮蔽源码和测试文件" if args.demo else "最近符合条件的多文件 MODIFY 提交，每次遮蔽按路径排序的最后一个文件",
                       "functional_controls": controls})
    (args.output / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = ["ChangeGuard 潜在遗漏检测评估", "", f"来源：{evaluation['source']}", f"快照：{evaluation['snapshot_id']}",
            f"分支：{evaluation['branch']}；tip：{evaluation['tip']}", f"案例选择：{evaluation['case_selection']}",
            f"遮蔽案例：{evaluation['case_count']}；K={evaluation['top_k']}；规则未给出建议：{evaluation['abstained_cases']}",
            f"规则结果：{evaluation['rules']}", f"历史修改频率基线：{evaluation['frequency_baseline']}", "",
            "合成功能对照：", *(json.dumps(case, ensure_ascii=False) for case in controls), "", "评估范围：", *evaluation["limitations"]]
    (args.output / "evaluation.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps({"source": evaluation["source"], "controls_passed": sum(case["passed"] for case in controls),
                      "controls_total": len(controls), "cases": evaluation["case_count"], "rules": evaluation["rules"],
                      "baseline": evaluation["frequency_baseline"], "output": str(args.output)}, ensure_ascii=False))
    if any(not case["passed"] for case in controls):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
