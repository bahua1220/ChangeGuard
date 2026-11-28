"""Deterministic comparison of two date ranges in the same mined snapshot."""

from datetime import date

import pandas as pd

from repolens.analytics import file_activity, filter_frames, metrics, module_activity
from repolens.sprints import coverage_note


METRIC_LABELS = {
    "commits": "提交数", "developers": "作者标识数", "files": "变更文件路径数",
    "added": "新增行", "deleted": "删除行", "churn": "变动行数", "days": "日历天数",
    "commits_per_day": "平均每日提交数",
}


def _period(commits, changes, sprint, authors, modules):
    start, end = date.fromisoformat(sprint["start"]), date.fromisoformat(sprint["end"])
    if start > end:
        raise ValueError("Sprint 开始日期不能晚于结束日期。")
    selected, files = filter_frames(commits, changes, start, end, authors, modules)
    stats = metrics(selected, files)
    stats["days"] = (end - start).days + 1
    stats["churn"] = stats["added"] + stats["deleted"]
    stats["commits_per_day"] = stats["commits"] / stats["days"]
    return {"sprint": dict(sprint), "stats": stats, "commits": selected, "changes": files}


def _paired_activity(left, right, group, activity):
    columns = [group, "commits", "added", "deleted", "churn"]
    paired = activity(left)[columns].merge(
        activity(right)[columns], on=group, how="outer", suffixes=("_a", "_b")
    )
    numeric = [column for column in paired if column != group]
    paired[numeric] = paired[numeric].apply(pd.to_numeric).fillna(0).astype(int)
    paired["churn_delta"] = paired["churn_b"] - paired["churn_a"]
    paired["combined_churn"] = paired["churn_a"] + paired["churn_b"]
    return paired.sort_values(["combined_churn", group], ascending=[False, True]).drop(columns="combined_churn").reset_index(drop=True)


def compare_sprints(meta, commits, changes, sprint_a, sprint_b, authors=(), modules=()):
    """Apply identical author/module filters independently to A and B (inclusive)."""
    a = _period(commits, changes, sprint_a, authors, modules)
    b = _period(commits, changes, sprint_b, authors, modules)
    rows = []
    for key, label in METRIC_LABELS.items():
        before, after = a["stats"][key], b["stats"][key]
        # A zero baseline has no defined percentage change, including 0 -> 0.
        rows.append({"metric": label, "a": before, "b": after, "delta": after - before,
                     "percent": (after - before) / before * 100 if before else None})
    warnings = []
    for label, period in (("A", a), ("B", b)):
        sprint = period["sprint"]
        warnings.extend(f"{label} · {sprint['name']}：{note}" for note in coverage_note(
            meta, commits, date.fromisoformat(sprint["start"]), date.fromisoformat(sprint["end"])
        ))
        if period["stats"]["commits"] == 0:
            warnings.append(f"{label} · {sprint['name']}：当前已采集数据及筛选条件下没有提交，不能据此断言该迭代没有开发活动。")
    if max(sprint_a["start"], sprint_b["start"]) <= min(sprint_a["end"], sprint_b["end"]):
        warnings.append("两个日期范围重叠，重叠日期的提交可能同时计入 A 和 B。")
    if a["stats"]["days"] != b["stats"]["days"]:
        warnings.append("两个 Sprint 时长不同；总量比较请结合平均每日提交数查看。")
    warnings.extend(meta.get("warnings", []))
    files = _paired_activity(a["changes"], b["changes"], "path", file_activity)
    files["scope"] = ["两期均有变更" if x and y else "仅 A 有变更" if x else "仅 B 有变更"
                      for x, y in zip(files["commits_a"], files["commits_b"])]
    return {
        "a": a, "b": b, "metrics": pd.DataFrame(rows), "files": files,
        "modules": _paired_activity(a["changes"], b["changes"], "module", module_activity),
        "warnings": list(dict.fromkeys(warnings)), "authors": list(authors), "module_filter": list(modules),
    }


def metric_table(result):
    table = result["metrics"].copy()
    for column in ("a", "b", "delta"):
        table[column] = table[column].map(lambda value: f"{value:,.2f}" if value != int(value) else f"{int(value):,}")
    table["percent"] = table["percent"].map(lambda value: "—（A 为 0）" if pd.isna(value) else f"{value:+.1f}%")
    return table.rename(columns={"metric": "指标", "a": "A", "b": "B", "delta": "差值 B − A", "percent": "变化率"})


def activity_table(table):
    return table.rename(columns={
        "module": "模块", "path": "文件路径", "commits_a": "A 提交数", "commits_b": "B 提交数",
        "added_a": "A 新增行", "added_b": "B 新增行", "deleted_a": "A 删除行", "deleted_b": "B 删除行",
        "churn_a": "A 变动行数", "churn_b": "B 变动行数", "churn_delta": "变动行数差值 B − A", "scope": "变更范围",
    })


def _escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def _markdown_table(table):
    return "\n".join([
        "| " + " | ".join(map(_escape, table.columns)) + " |",
        "| " + " | ".join("---" for _ in table.columns) + " |",
        *("| " + " | ".join(map(_escape, row)) + " |" for row in table.itertuples(index=False, name=None)),
    ])


def export_comparison(meta, result, timezone):
    """A factual export with explicit provenance and no model dependency."""
    lines = ["# Sprint 对比报告", "", "程序统计生成，未调用 AI。", "",
             f"仓库：{_escape(meta.get('source_url') or meta['path'])}",
             f"分支：{_escape(meta['branch'])} · tip：{meta['tip']} · 快照：{meta['id']}",
             f"时区：{_escape(timezone)}；日期依据：committer date，含首尾。",
             f"作者筛选：{_escape(', '.join(result['authors']) or '全部')}",
             f"模块筛选：{_escape(', '.join(result['module_filter']) or '全部')}", ""]
    for label in ("a", "b"):
        sprint = result[label]["sprint"]
        lines.append(f"{label.upper()}：{_escape(sprint['name'])} · {sprint['start']} 至 {sprint['end']}")
    lines.extend(["", "## 指标", "", _markdown_table(metric_table(result)), "",
                  "差值与变化率均按 B 相对 A 计算；A 为 0 时不计算变化率。", "",
                  "## 模块变化", "", _markdown_table(activity_table(result["modules"])), "",
                  "## 文件变化", "", _markdown_table(activity_table(result["files"].head(100)))])
    if len(result["files"]) > 100:
        lines.append(f"\n仅导出变动量最高的 100 / {len(result['files'])} 个文件路径；页面表格可查看全部。")
    lines.extend(["", "## 统计说明与覆盖限制", "",
                  "- 比较同一分支快照中两个日期范围的开发活动，不比较两个版本的完整源码差异。",
                  "- 文件按路径计数，重命名前后不合并；仅 A/B 有变更不代表文件新增或删除。",
                  "- 作者标识按邮箱区分；提交数及代码行数不代表质量、工时或课程贡献比例。",
                  "- 模块按首级目录划分；一条提交可同时触及多个模块，模块提交数不能直接相加。",
                  "- 变动行数 = 新增行 + 删除行；merge 按当前快照口径处理。",
                  *("- " + _escape(warning) for warning in result["warnings"])])
    return "\n".join(lines) + "\n"
