"""Download public GitHub histories to an app-owned cache without checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from repolens.mining import RepositoryError, git, inspect_repository
from repolens.network import validate_proxy

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "data" / "github_repositories"


def normalize_github_url(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("github.com/"):
        value = "https://" + value
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise RepositoryError("GitHub 链接格式不正确，请粘贴仓库首页地址。") from exc
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
        raise RepositoryError("请输入公开 GitHub 仓库首页的 HTTPS 链接，例如 https://github.com/ishepard/pydriller。")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise RepositoryError("请使用仓库首页链接；分支请填写在下方，不要粘贴 /tree/ 或 /blob/ 页面地址。")
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) or name in (".", ".."):
        raise RepositoryError("GitHub 用户名或仓库名格式不正确。")
    return f"https://github.com/{owner.lower()}/{name.lower()}.git"


def _run_git(args, *, cwd=None, proxy=None):
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_LFS_SKIP_SMUDGE": "1"})
    environment.pop("GIT_ASKPASS", None)
    environment.pop("SSH_ASKPASS", None)
    proxy_args = ["-c", "http.proxy=" + validate_proxy(proxy)] if proxy else []
    try:
        process = subprocess.Popen([
            "git", "-c", "credential.helper=", "-c", "core.askPass=", "-c", "http.followRedirects=initial",
            "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", "-c", "protocol.ssh.allow=never",
            "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=30",
            *proxy_args,
            *args,
        ], cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0,
            start_new_session=os.name != "nt")
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            # git.exe on Windows launches another git and remote-https process.
            # Kill only this owned tree, otherwise inherited pipes can keep a
            # nominal subprocess timeout blocked indefinitely.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.stdout.close()
                process.stderr.close()
            raise RepositoryError("GitHub 下载超时，请减小历史深度或检查本机连接 GitHub 的网络。")
    except FileNotFoundError as exc:
        raise RepositoryError("未找到 Git，请安装 Git 并加入 PATH。") from exc
    if process.returncode:
        # No terminal login, credential manager, or raw transport errors in the UI.
        error = stderr.lower()
        if "remote branch" in error or "invalid branch" in error or "not a valid branch" in error:
            raise RepositoryError("没有找到指定分支或分支名无效，请检查分支名称；留空使用默认分支。")
        if any(text in error for text in ("not found", "authentication", "could not read username", "terminal prompts disabled", "could not read password")):
            raise RepositoryError("无法读取该仓库：请确认地址正确且仓库公开。当前不接入私有仓库登录。")
        if any(text in error for text in ("failed to connect", "could not connect", "could not resolve", "connection was reset", "connection timed out", "operation too slow")):
            raise RepositoryError("本机 Git 无法连接 GitHub，或传输中断/过慢。请检查网络及 Git 代理设置后重试；浏览器能打开 GitHub 不一定代表 Git 下载可用。")
        if "certificate" in error or "ssl" in error or "schannel" in error:
            raise RepositoryError("Git 的 HTTPS 连接或证书校验失败，请检查本机 Git 网络与证书配置。")
        raise RepositoryError("GitHub 下载失败。请检查仓库地址、分支和本机 Git 网络连接；已有缓存保留。")
    return stdout.strip()


def download_github(value: str, branch="", depth=300, refresh=False, cache_root=DEFAULT_CACHE, proxy=None) -> dict:
    url = normalize_github_url(value)
    branch = branch.strip()
    if not 2 <= int(depth) <= 2000:
        raise RepositoryError("下载历史深度必须介于 2 与 2000。")
    if branch:
        if branch.startswith("-"):
            raise RepositoryError("分支名格式不正确。")
        _run_git(["check-ref-format", "--branch", branch], proxy=proxy)
    root = Path(cache_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache_id = hashlib.sha256(json.dumps([url, branch, int(depth)]).encode()).hexdigest()[:16]
    name = url.rsplit("/", 1)[-1][:-4]
    target = (root / f"github-{name[:50]}-{cache_id}").resolve()
    if target.parent != root:
        raise RepositoryError("下载缓存路径无效。")
    marker = target / ".git" / "repolens-source.json"
    cached = target.exists()
    if cached:
        if not marker.is_file():
            raise RepositoryError("下载目录不属于有效的 ChangeGuard 缓存，请改用本地路径打开或联系维护者检查。")
        try:
            saved = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RepositoryError("下载缓存的来源记录不可读取，未修改已有目录。") from exc
        if not isinstance(saved, dict) or saved.get("url") != url or saved.get("depth") != int(depth) or saved.get("requested_branch") != branch:
            raise RepositoryError("下载缓存来源不匹配，未修改已有目录。")
        info = inspect_repository(str(target))
        if refresh:
            # Only app-owned, never-checked-out caches are updated. User local repos
            # never go through this path, and no reset/checkout is needed.
            current = git(target, "symbolic-ref", "HEAD")
            short = current.removeprefix("refs/heads/")
            remote_ref = f"refs/remotes/origin/{short}"
            _run_git(["fetch", "--no-tags", f"--depth={int(depth)}", "origin", f"+refs/heads/{short}:{remote_ref}"], cwd=str(target), proxy=proxy)
            git(target, "update-ref", current, git(target, "rev-parse", remote_ref))
            info = inspect_repository(str(target))
    else:
        with tempfile.TemporaryDirectory(prefix="download-", dir=root) as staging:
            stage = Path(staging).resolve()
            # Verify the paths before TemporaryDirectory's recursive cleanup / rename.
            if stage.parent != root:
                raise RepositoryError("临时下载路径无效。")
            clone_path = stage / "repository"
            args = ["clone", "--no-checkout", "--single-branch", "--no-tags", f"--depth={int(depth)}"]
            if branch:
                args += ["--branch", branch]
            args += ["--", url, str(clone_path)]
            _run_git(args, proxy=proxy)
            info = inspect_repository(str(clone_path))
            (clone_path / ".git" / "repolens-source.json").write_text(json.dumps({"url": url, "requested_branch": branch, "depth": int(depth)}), encoding="utf-8")
            if target.exists():
                raise RepositoryError("另一个下载任务已创建该缓存，请重新点击打开。")
            clone_path.rename(target)
        info = inspect_repository(str(target))
    info.update({"name": url.removeprefix("https://github.com/").removesuffix(".git"), "source_url": url.removesuffix(".git"), "download_cached": cached, "download_refreshed": bool(cached and refresh)})
    return info
