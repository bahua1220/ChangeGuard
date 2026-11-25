"""Stable repository identity and range coverage for saved sprints."""

from datetime import date
from pathlib import Path


def repository_key(meta):
    if meta.get("source_url"):
        return meta["source_url"].rstrip("/").removesuffix(".git").lower()
    return str(Path(meta["path"]).resolve()).casefold()


def coverage_note(meta, commits, start, end):
    notes = []
    if start < min(commits["date"]) or end > max(commits["date"]):
        notes.append("Sprint 日期超出当前已采集提交的日期跨度；范围外可能无提交，也可能尚未下载。")
    if meta.get("is_shallow") or len(meta["hashes"]) < meta["total_commits"]:
        notes.append("当前历史不完整，本 Sprint 报告仅基于已采集提交，不能保证覆盖整个 Sprint。")
    return notes
