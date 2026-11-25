"""One filter pipeline shared by charts, details and reports."""

import pandas as pd

COMMIT_COLUMNS = ["hash", "message", "author_name", "author_email", "committed_at", "authored_at", "is_merge"]
CHANGE_COLUMNS = ["commit_hash", "old_path", "new_path", "path", "module", "change_type", "added_lines", "deleted_lines", "diff", "diff_truncated"]


def frames(snapshot, timezone="Asia/Shanghai"):
    commits = pd.DataFrame(snapshot["commits"], columns=COMMIT_COLUMNS)
    changes = pd.DataFrame(snapshot["changes"], columns=CHANGE_COLUMNS)
    commits["time"] = pd.to_datetime(commits["committed_at"], utc=True).dt.tz_convert(timezone)
    commits["date"] = commits["time"].dt.date
    commits["author_id"] = commits.apply(lambda r: r["author_email"].strip().lower() or r["author_name"], axis=1) if not commits.empty else pd.Series(dtype=str)
    commits["subject"] = commits["message"].str.split("\n").str[0]
    return commits, changes


def filter_frames(commits, changes, start, end, authors=(), modules=()):
    mask = (commits["date"] >= start) & (commits["date"] <= end)
    if authors:
        mask &= commits["author_id"].isin(authors)
    selected = commits.loc[mask].copy()
    selected_changes = changes[changes["commit_hash"].isin(selected["hash"])].copy()
    if modules:
        selected_changes = selected_changes[selected_changes["module"].isin(modules)].copy()
        selected = selected[selected["hash"].isin(selected_changes["commit_hash"])].copy()
    return selected, selected_changes


def metrics(commits, changes):
    return {
        "commits": len(commits), "developers": commits["author_id"].nunique(),
        "files": changes["path"].nunique(),
        "added": int(changes["added_lines"].sum()),
        "deleted": int(changes["deleted_lines"].sum()),
        "merges": int(commits["is_merge"].sum()),
    }


def daily_activity(commits, changes):
    if commits.empty:
        return pd.DataFrame(columns=["date", "commits", "added", "deleted"])
    counts = commits.groupby("date").size().rename("commits")
    lines = changes.merge(commits[["hash", "date"]], left_on="commit_hash", right_on="hash")
    lines = lines.groupby("date")[["added_lines", "deleted_lines"]].sum().rename(columns={"added_lines": "added", "deleted_lines": "deleted"})
    result = counts.to_frame().join(lines).fillna(0)
    full_dates = pd.date_range(min(commits["date"]), max(commits["date"]), freq="D").date
    return result.reindex(full_dates, fill_value=0).rename_axis("date").reset_index()


def file_activity(changes):
    if changes.empty:
        return pd.DataFrame(columns=["path", "commits", "added", "deleted", "churn"])
    result = changes.groupby("path").agg(commits=("commit_hash", "nunique"), added=("added_lines", "sum"), deleted=("deleted_lines", "sum")).reset_index()
    result["churn"] = result["added"] + result["deleted"]
    return result.sort_values(["commits", "churn", "path"], ascending=[False, False, True])


def module_activity(changes):
    if changes.empty:
        return pd.DataFrame(columns=["module", "commits", "files", "added", "deleted", "churn"])
    result = changes.groupby("module").agg(commits=("commit_hash", "nunique"), files=("path", "nunique"), added=("added_lines", "sum"), deleted=("deleted_lines", "sum")).reset_index()
    result["churn"] = result["added"] + result["deleted"]
    return result.sort_values("churn", ascending=False)


def developer_activity(commits, changes):
    if commits.empty:
        return pd.DataFrame(columns=["author_id", "name", "commits", "files", "modules", "added", "deleted"])
    result = commits.groupby("author_id").agg(name=("author_name", "first"), commits=("hash", "nunique"))
    joined = changes.merge(commits[["hash", "author_id"]], left_on="commit_hash", right_on="hash")
    stats = joined.groupby("author_id").agg(files=("path", "nunique"), modules=("module", lambda x: ", ".join(sorted(set(x)))), added=("added_lines", "sum"), deleted=("deleted_lines", "sum"))
    result = result.join(stats)
    result["modules"] = result["modules"].fillna("")
    for col in ("files", "added", "deleted"):
        result[col] = result[col].fillna(0).astype(int)
    return result.reset_index().sort_values(["commits", "author_id"], ascending=[False, True])
