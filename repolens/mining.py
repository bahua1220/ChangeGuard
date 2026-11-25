"""Read local repositories without checking out files or changing Git settings."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydriller import Git
from git import Repo
from git.exc import GitCommandError
from repolens.methods import extract_methods

MINING_VERSION = 4
DIFF_LIMIT = 12_000


class RepositoryError(ValueError):
    pass


def mining_error(sha: str, stage: str, error: Exception) -> str:
    prefix = f"读取提交 {sha[:10]} 失败（{stage}）。本次分析未保存。"
    if isinstance(error, GitCommandError):
        detail = str(error.stderr or "").strip()
        # Surface Git's actionable reason, without exposing credential-bearing URLs.
        detail = re.sub(r"(https?://)[^\s/@]+@", r"\1[redacted]@", detail)
        detail = re.sub(r"(?i)([?&](?:token|access_token|key)=)[^\s&]+", r"\1[redacted]", detail)
        if "bad object" in detail.lower() or "bad revision" in detail.lower():
            hint = "Git 缺少用于比较的提交对象；浅克隆的下载边界不能计算 diff。请重启应用加载最新的边界处理，再复用缓存重新分析；仍失败时可增大下载深度。"
        else:
            hint = "Git 无法读取本次差异，请根据下方原始原因检查仓库。"
        return f"{prefix}\n\n{hint}\n\nGit 原因：{detail[:800] or '未提供错误详情'}"
    return f"{prefix}\n\n错误类型：{type(error).__name__}。请保留该提交编号以便排查。"


class ReadOnlyGit(Git):
    def _open_repository(self):
        # Upstream Git._open_repository writes a blame setting into .git/config.
        # Mining needs no blame configuration; keep the user's repository untouched.
        self._repo = Repo(str(self.path))
        if self._conf.get("main_branch") is None:
            self._discover_main_branch(self._repo)


def git(path: str | Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(path), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RepositoryError("未找到 Git，请安装 Git 并加入 PATH。") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepositoryError("Git 操作超时，请缩小分析范围后重试。") from exc
    if result.returncode:
        raise RepositoryError(result.stderr.strip() or "Git 操作失败。")
    return result.stdout.strip()


def inspect_repository(path: str) -> dict:
    candidate = Path(path.strip().strip('"')).expanduser()
    if not candidate.is_dir():
        raise RepositoryError("目录不存在，请输入本机 Git 仓库路径。")
    if git(candidate, "rev-parse", "--is-bare-repository") == "true":
        raise RepositoryError("当前版本需要包含工作目录的仓库，不支持 bare 仓库。")
    root = git(candidate, "rev-parse", "--show-toplevel")
    branches = git(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes").splitlines()
    branches = [b for b in branches if not b.endswith("/HEAD")]
    try:
        head = git(root, "rev-parse", "--verify", "HEAD")
    except RepositoryError as exc:
        raise RepositoryError("仓库还没有提交，请先创建一条提交。") from exc
    if not branches:
        branches = [head]
    current = git(root, "symbolic-ref", "-q", "HEAD") if not git(root, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD" else head
    if current not in branches:
        branches.insert(0, current)
    return {"path": str(Path(root).resolve()), "name": Path(root).name, "branches": branches, "current": current}


def short_branch(ref: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref[:12] if len(ref) == 40 else ref


def analysis_spec(info: dict, branch: str, limit: int, include_merges: bool) -> dict:
    if not 1 <= limit <= 2000:
        raise RepositoryError("提交上限必须介于 1 与 2000。")
    tip = git(info["path"], "rev-parse", "--verify", "--end-of-options", f"{branch}^{{commit}}")
    args = [] if include_merges else ["--no-merges"]
    is_shallow = git(info["path"], "rev-parse", "--is-shallow-repository") == "true"
    exclusions = []
    if is_shallow:
        shallow_path = Path(git(info["path"], "rev-parse", "--git-path", "shallow"))
        if not shallow_path.is_absolute():
            shallow_path = Path(info["path"]) / shallow_path
        # At a shallow boundary, Git treats missing parents like a root commit.
        # Exclude these commits instead of reporting whole files as new additions.
        exclusions = ["^" + sha for sha in shallow_path.read_text(encoding="ascii").splitlines() if sha]
    revisions = [tip, *exclusions]
    total = int(git(info["path"], "rev-list", "--count", *args, *revisions))
    hashes = git(info["path"], "rev-list", "--topo-order", f"--max-count={limit}", *args, *revisions).splitlines()
    spec = {
        "path": info["path"], "name": info["name"], "branch": branch,
        "tip": tip, "limit": limit, "include_merges": include_merges,
        "total_commits": total, "hashes": hashes, "mining_version": MINING_VERSION,
        "is_shallow": is_shallow, "source_url": info.get("source_url"),
    }
    spec["id"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:24]
    return spec


def mine(spec: dict, progress: Callable[[int, int], None] | None = None) -> dict:
    commits, changes, warnings = [], [], []
    repository = ReadOnlyGit(spec["path"])
    # Resolve a fixed list of hashes first: a moving branch cannot mix snapshots.
    for index, sha in enumerate(spec["hashes"]):
        stage = "读取提交信息"
        try:
            commit = repository.get_commit(sha)
            merge = len(commit.parents) > 1
            commits.append({
                "hash": sha, "message": commit.msg,
                "author_name": commit.author.name or "Unknown",
                "author_email": commit.author.email or "",
                "committed_at": commit.committer_date.astimezone(timezone.utc).isoformat(),
                "authored_at": commit.author_date.astimezone(timezone.utc).isoformat(),
                "is_merge": merge,
            })
            # PyDriller does not reliably expose per-file merge diffs; never invent them.
            if not merge:
                stage = "读取文件差异"
                for file in commit.modified_files:
                    diff = file.diff or ""
                    old_path = Path(file.old_path).as_posix() if file.old_path else None
                    new_path = Path(file.new_path).as_posix() if file.new_path else None
                    path = new_path or old_path or "(unknown)"
                    changes.append({
                        "commit_hash": sha, "old_path": old_path,
                        "new_path": new_path, "path": path,
                        "module": path.split("/")[0] if "/" in path else "(root)",
                        "change_type": file.change_type.name,
                        "added_lines": file.added_lines,
                        "deleted_lines": file.deleted_lines,
                        "diff": diff[:DIFF_LIMIT], "diff_truncated": len(diff) > DIFF_LIMIT,
                        **extract_methods(file),
                    })
            if progress:
                progress(index + 1, len(spec["hashes"]))
        except Exception as exc:
            # An incomplete scan must not be saved as a successful cached analysis.
            repository.clear()
            repository.repo.close()
            raise RepositoryError(mining_error(sha, stage, exc)) from exc
    repository.clear()
    repository.repo.close()
    if any(c["is_merge"] for c in commits):
        warnings.append("提交数包含 merge；文件数与增删行数只统计非 merge 提交，以避免重复计算。")
    if spec.get("is_shallow"):
        warnings.append("这是部分下载的浅克隆历史，不能代表 GitHub 仓库全部历史。缺少父提交的下载边界已排除，避免误把整个文件计算为新增。覆盖总数仅指本机已下载且可分析的提交。")
    if len(commits) < spec["total_commits"]:
        warnings.append(f"仅采集分支拓扑遍历中的最近 {len(commits)} 条符合条件的提交，非完整历史；日期筛选仅作用于已采集数据。")
    warnings.append("模块按首级目录分组；文件按路径统计，重命名前后暂不合并。增删行数不能衡量工作质量或实际工时。")
    return {"meta": {**spec, "created_at": datetime.now(timezone.utc).isoformat(), "warnings": warnings}, "commits": commits, "changes": changes}
