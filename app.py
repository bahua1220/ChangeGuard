from __future__ import annotations

import html
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from repolens.analytics import daily_activity, developer_activity, file_activity, filter_frames, frames, metrics, module_activity
from repolens.demo import create_demo
from repolens.mining import MINING_VERSION, RepositoryError, analysis_spec, inspect_repository, mine, short_branch
from repolens.remote import download_github
from repolens.network import windows_proxy
from repolens.reports import SummaryError, build_ai_payload, export_markdown, factual_report, fingerprint, generate_ai_report, summary_key
from repolens.storage import delete_sprint, list_sprints, load_snapshot, load_summary, recent_runs, save_snapshot, save_sprint, save_summary
from repolens.sprints import coverage_note, repository_key

ROOT = Path(__file__).resolve().parent
APP_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
load_dotenv(ROOT / ".env")
st.set_page_config(page_title="ChangeGuard · Git 历史分析", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

COLORS = ["#087f8c", "#6376c5", "#e9a23b", "#3a9b78", "#c56b82", "#7296ad"]
px.defaults.color_discrete_sequence = COLORS

st.markdown("""
<style>
.block-container {max-width: 1480px; padding-top: 2.1rem; padding-bottom: 3rem;}
[data-testid="stSidebar"] {border-right: 1px solid #dfe5ee;}
[data-testid="stSidebar"] .block-container {padding-top: 1.5rem;}
.brand {font-size: 1.8rem; font-weight: 800; letter-spacing: -.06em; color:#173954;}
.brand em {font-style:normal; color:#087f8c;}
.eyebrow {font-size:.78rem; letter-spacing:.15em; font-weight:700; color:#087f8c; margin-bottom:.6rem;}
.hero {background:#122c43; padding:2rem 2.2rem; border-radius:18px; margin-bottom:1.4rem; color:white;}
.hero h1 {color:white; font-size:2.4rem; letter-spacing:-.04em; margin:0 0 .7rem; padding:0;}
.hero p {color:#c3d4e3; font-size:1rem; margin:0; line-height:1.7;}
.hero .eyebrow {color:#75d8cd;}
.tag {display:inline-block; background:#254357; color:#ccece8; border-radius:6px; padding:4px 10px; margin-top:1rem; font-size:.8rem;}
[data-testid="stMetric"] {background:white; border:1px solid #e0e7ef; border-radius:12px; padding:1rem 1.15rem;}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;}
.section-title {font-size:1.15rem; font-weight:700; margin:.4rem 0 .25rem; color:#173954;}
.muted {color:#62758a; font-size:.92rem; line-height:1.7;}
.feature {background:white; border:1px solid #e0e7ef; padding:1.5rem; border-radius:14px; min-height:180px;}
.feature h3 {font-size:1.12rem; padding:0; margin:.8rem 0 .6rem;}
.feature p {font-size:.94rem; color:#62758a; line-height:1.7;}
.feature .symbol {color:#087f8c; font-size:1.5rem;}
.stTabs [data-baseweb="tab-list"] {gap:1.3rem; border-bottom:1px solid #dfe5ee; margin-top:.5rem;}
.stTabs [data-baseweb="tab"] {font-size:1rem; padding-bottom: .8rem;}
div[data-testid="stAlert"] {border-radius:10px;}
</style>
""", unsafe_allow_html=True)


def plot(fig, key):
    fig.update_layout(
        template="plotly_white", height=320, margin=dict(l=12, r=12, t=24, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color="#4b6075", size=13),
        legend=dict(orientation="h", y=1.15, x=0),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e7edf4", zeroline=False)
    st.plotly_chart(fig, width="stretch", key=key)


def title(text, caption=None):
    st.markdown(f'<div class="section-title">{html.escape(text)}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def analyze(info, branch, limit, include_merges, force=False):
    spec = analysis_spec(info, branch, int(limit), include_merges)
    snapshot = None if force else load_snapshot(spec["id"])
    if snapshot is None:
        bar = st.progress(0, text="正在读取 Git 历史…")
        try:
            snapshot = mine(spec, lambda done, total: bar.progress(done / max(1, total), text=f"正在读取提交 {done} / {total}"))
            save_snapshot(snapshot)
        finally:
            bar.empty()
    st.session_state["snapshot"] = snapshot


def display_commit(sha, commits, changes, key):
    match = commits[commits["hash"] == sha]
    if match.empty:
        st.info("该提交不在当前筛选范围内。")
        return
    row = match.iloc[0]
    st.code(sha, language=None)
    st.text(f"{row['author_name']} · {row['author_email']} · {row['time'].strftime('%Y-%m-%d %H:%M %Z')}")
    st.text(row["message"])
    files = changes[changes["commit_hash"] == sha]
    if files.empty:
        st.info("没有可展示的文件变化。Merge 提交的逐文件 diff 在当前版本中不统计。")
        return
    for index, file in enumerate(files.itertuples()):
        with st.expander(f"{file.change_type} · {file.path}   +{file.added_lines} / −{file.deleted_lines}", expanded=len(files) == 1):
            if file.old_path and file.new_path and file.old_path != file.new_path:
                st.text(f"{file.old_path} → {file.new_path}")
            st.markdown("**Changed methods · 变更方法**")
            method_rows = file.changed_methods if isinstance(file.changed_methods, list) else []
            if method_rows:
                table = pd.DataFrame(method_rows)
                table["version"] = table["version"].map({"before": "变更前", "after": "变更后"})
                st.dataframe(table[["signature", "version", "start_line", "end_line"]].rename(columns={"signature": "方法签名", "version": "源码版本", "start_line": "起始行", "end_line": "结束行"}), hide_index=True, width="stretch")
                st.caption("列出与增删行相交的方法位置。同一方法可同时显示变更前和变更后；不追踪跨文件移动或重命名。")
            else:
                st.caption({"unsupported": "该文件语言或类型不支持方法解析。", "none": "未识别到方法内部的行变更（可能仅修改模块级代码、注释或路径）。", "error": "方法解析失败，文件统计和 diff 仍可查看。"}.get(file.method_status, "此缓存尚未采集方法信息，请重新分析仓库。"))
            if file.diff_truncated:
                st.warning("差异较长，仅保存并展示前 12,000 个字符；统计行数仍来自完整变更记录。")
            if file.diff:
                st.code(file.diff, language="diff", line_numbers=False)
            else:
                st.caption("没有可展示的文本 diff，可能是纯重命名、空文件或二进制变更。")


with st.sidebar:
    st.markdown('<div class="brand">◈ Change<em>Guard</em></div>', unsafe_allow_html=True)
    st.caption("An Explainable Change Completeness Analysis Tool Based on Git History")
    st.caption("仓库演化 · 可视化 · 智能摘要")
    st.divider()
    if st.button("载入演示仓库", width="stretch", type="primary", help="创建并分析一个包含 18 条合成提交的本地仓库。"):
        try:
            path = create_demo()
            info = inspect_repository(path)
            st.session_state["repo_input"] = path
            st.session_state["repo_info"] = info
            st.session_state["source_mode"] = "本地路径"
            analyze(info, info["current"], 300, False)
            demo_key = repository_key(st.session_state["snapshot"]["meta"])
            if not list_sprints(demo_key):
                save_sprint(demo_key, "Sprint 1", "2026-11-09", "2026-11-14")
                save_sprint(demo_key, "Sprint 2", "2026-11-15", "2026-11-22")
        except (RepositoryError, RuntimeError, ValueError) as exc:
            st.error(str(exc))
    st.caption("演示数据为合成记录，不代表真实开发活动。")
    source_mode = st.radio("仓库来源", ["GitHub 链接", "本地路径"], horizontal=True, key="source_mode")
    if source_mode == "GitHub 链接":
        detected_proxy = windows_proxy()
        with st.form("github_repo"):
            github_url = st.text_input("GitHub 仓库链接", placeholder="https://github.com/ishepard/pydriller")
            github_branch = st.text_input("下载分支（可留空）", placeholder="留空使用默认分支")
            github_depth = st.number_input("下载历史深度", min_value=2, max_value=2000, value=100, step=50)
            refresh_remote = st.checkbox("从 GitHub 更新已有下载", value=False)
            st.caption("支持公开仓库，无需 GitHub Token。首次下载部分历史，仅下载指定或默认分支；再次打开可复用本机缓存。")
            if st.form_submit_button("下载并分析", width="stretch", type="primary"):
                try:
                    with st.spinner("正在从 GitHub 下载提交历史，首次下载可能需要一些时间…"):
                        info = download_github(github_url, github_branch, int(github_depth), refresh_remote, proxy=detected_proxy)
                    st.session_state["repo_info"] = info
                    st.session_state["repo_input"] = info["path"]
                    st.session_state.pop("snapshot", None)
                    analyze(info, info["current"], int(github_depth), False)
                    st.success("已复用本机下载缓存。" if info["download_cached"] and not refresh_remote else "GitHub 历史已下载并完成分析。")
                except RepositoryError as exc:
                    st.session_state.pop("repo_info", None)
                    st.session_state.pop("snapshot", None)
                    st.error(str(exc))
    else:
        with st.form("open_repo"):
            path = st.text_input("本地 Git 仓库路径", key="repo_input", placeholder="D:/projects/my-repository")
            if st.form_submit_button("读取仓库", width="stretch"):
                try:
                    info = inspect_repository(path)
                    previous = st.session_state.get("repo_info", {})
                    if previous.get("path") != info["path"]:
                        st.session_state.pop("snapshot", None)
                    st.session_state["repo_info"] = info
                except RepositoryError as exc:
                    st.session_state.pop("repo_info", None)
                    st.session_state.pop("snapshot", None)
                    st.error(str(exc))
    info = st.session_state.get("repo_info")
    if info:
        branch = st.selectbox("分析分支", info["branches"], index=info["branches"].index(info["current"]), format_func=short_branch, key="branch_" + info["path"])
        limit = st.number_input("最多采集提交数", min_value=1, max_value=2000, value=300, step=50)
        include_merges = st.checkbox("提交数包含 merge", value=False)
        force = st.checkbox("重新采集（忽略缓存）", value=False)
        if st.button("分析仓库", width="stretch", type="primary"):
            try:
                analyze(info, branch, limit, include_merges, force)
            except RepositoryError as exc:
                st.error(str(exc))
        st.caption("读取已提交历史；未提交修改不参与分析。")
    with st.expander("最近分析"):
        all_histories = recent_runs()
        histories = [r for r in all_histories if r.get("mining_version") == MINING_VERSION]
        if any(r.get("mining_version") != MINING_VERSION for r in all_histories):
            st.caption("旧版分析需重新采集以补充方法信息；已有 GitHub 下载可直接复用，无需勾选更新下载。")
        if histories:
            chosen = st.selectbox("选择已缓存快照", histories, format_func=lambda r: f"{r['name']} · {short_branch(r['branch'])} · {r['tip'][:7]}")
            if st.button("打开缓存", width="stretch"):
                st.session_state["snapshot"] = load_snapshot(chosen["id"])
        else:
            st.caption("分析结果会保存在本机 SQLite。")
    st.divider()
    timezone = st.selectbox("展示与统计时区", ["Asia/Shanghai", "UTC"], key="timezone")
    with st.expander("AI 模型设置"):
        base_url = st.text_input("API Base URL", value=os.getenv("REPOLENS_AI_BASE_URL", "https://api.openai.com/v1"))
        model = st.text_input("模型名称", value=os.getenv("REPOLENS_AI_MODEL", ""), placeholder="填写服务商提供的模型 ID")
        api_key = st.text_input("API Key", value=os.getenv("REPOLENS_AI_API_KEY", ""), type="password")
        st.caption("兼容 Chat Completions + JSON 输出。本地服务可不填密钥。密钥不写入数据库。")
    st.caption(f"ChangeGuard {APP_VERSION} · Local-first")


snapshot = st.session_state.get("snapshot")
if snapshot is None:
    st.markdown('''<div class="hero"><div class="eyebrow">REPOSITORY EVOLUTION, MADE READABLE</div>
    <h1>看见代码如何演化。</h1><p>从分散的 Git 记录，到清晰的开发脉络。<br>探索提交、开发者与文件变化，为下一次 Sprint 回顾准备有依据的报告。</p>
    <span class="tag">PyDriller + Interactive Analytics + AI Summaries</span></div>''', unsafe_allow_html=True)
    st.info("从左侧输入公开 GitHub 仓库链接，点击「下载并分析」；也可载入演示仓库或使用本地路径。")
    for col, (symbol, name, text) in zip(st.columns(3), [
        ("◷", "读懂开发节奏", "按日期、开发者与模块探索提交趋势，定位值得进一步查看的变化。"),
        ("▤", "回到代码本身", "从文件修改排行深入到具体提交，直接查看代码差异和重命名记录。"),
        ("◇", "让总结有据可查", "先生成准确的统计报告；连接模型后，查看附带提交与文件引用的 AI 摘要。"),
    ]):
        with col:
            st.markdown(f'<div class="feature"><div class="symbol">{symbol}</div><h3>{name}</h3><p>{text}</p></div>', unsafe_allow_html=True)
    st.markdown("### 一个场景，走完完整流程")
    st.write("选择仓库与分支 → 筛选 Sprint 范围 → 探索图表与 diff → 核查摘要依据 → 导出报告。")
    st.stop()

meta = snapshot["meta"]
commits, changes = frames(snapshot, timezone)
st.markdown(f'''<div class="hero"><div class="eyebrow">REPOSITORY WORKSPACE</div>
<h1>{html.escape(meta['name'])}</h1><p>从开发节奏到具体代码，让每一段变化都有迹可循。</p>
<span class="tag">{html.escape(short_branch(meta['branch']))} &nbsp; / &nbsp; {meta['tip'][:10]} &nbsp; / &nbsp; {len(commits)} commits</span></div>''', unsafe_allow_html=True)
if Path(meta["path"]).name == "demo_repository":
    st.caption("演示模式 · 以下数据来自本机生成的合成 Git 仓库。")
if meta.get("source_url"):
    st.caption("GitHub 来源：" + meta["source_url"])
if meta.get("is_shallow"):
    st.warning("当前为部分下载的历史，不能代表仓库全部开发过程。缺少父提交的下载边界已排除；需要更早的历史时，请增大下载深度。")
if len(commits) < meta["total_commits"]:
    st.warning(f"当前采集 {len(commits)} / {meta['total_commits']} 条符合条件的提交。所有日期筛选和报告仅覆盖已采集数据。")
if commits.empty:
    st.info("当前快照没有符合条件的提交，请更换分支或采集选项。")
    st.stop()

repo_key = repository_key(meta)
sprints = list_sprints(repo_key)
sprint_map = {item["id"]: item for item in sprints}
sprint_select_key = "sprint_select_" + repo_key
pending_key = "sprint_pending_" + repo_key
if pending_key in st.session_state:
    st.session_state[sprint_select_key] = st.session_state.pop(pending_key)
if st.session_state.get(sprint_select_key, "custom") not in ["custom", *sprint_map]:
    st.session_state[sprint_select_key] = "custom"
with st.container(border=True):
    title("Sprint 工作区", "保存迭代日期后，可直接切换对应图表和变化报告；配置在本机持久保存。")
    sprint_id = st.selectbox("选择 Sprint", ["custom", *sprint_map], format_func=lambda value: "自定义日期范围" if value == "custom" else sprint_map[value]["name"], key=sprint_select_key)
    active_sprint = sprint_map.get(sprint_id)
    with st.expander("创建或编辑 Sprint"):
        edit_key = "edit_sprint_" + repo_key
        if st.session_state.get(edit_key, "new") not in ["new", *sprint_map]:
            st.session_state[edit_key] = "new"
        editing = st.selectbox("编辑目标", ["new", *sprint_map], format_func=lambda value: "新建 Sprint" if value == "new" else sprint_map[value]["name"], key=edit_key)
        existing = sprint_map.get(editing)
        with st.form("sprint_form_" + repo_key + editing):
            sprint_name = st.text_input("Sprint 名称", value=existing["name"] if existing else "", placeholder="例如 Sprint 1", max_chars=100)
            sprint_dates = st.date_input("Sprint 起止日期（含首尾）", value=(date.fromisoformat(existing["start"]), date.fromisoformat(existing["end"])) if existing else (min(commits["date"]), max(commits["date"])))
            if st.form_submit_button("保存 Sprint", type="primary"):
                try:
                    if len(sprint_dates) != 2:
                        raise ValueError("请选择完整的 Sprint 起止日期。")
                    saved_id = save_sprint(repo_key, sprint_name, *sprint_dates, sprint_id=existing["id"] if existing else None)
                    st.session_state[pending_key] = saved_id
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if existing and st.button("删除该 Sprint", key="delete_sprint_" + existing["id"]):
            delete_sprint(repo_key, existing["id"])
            st.session_state[pending_key] = "custom" if sprint_id == existing["id"] else sprint_id
            st.rerun()

with st.container(border=True):
    date_col, author_col, module_col = st.columns([1.3, 1, 1])
    key = meta["id"] + timezone
    with date_col:
        date_values = (date.fromisoformat(active_sprint["start"]), date.fromisoformat(active_sprint["end"])) if active_sprint else (min(commits["date"]), max(commits["date"]))
        selected_dates = st.date_input("日期范围（含首尾）", value=date_values, disabled=bool(active_sprint), key="dates_" + key + (str(active_sprint) if active_sprint else "custom"))
    with author_col:
        author_options = dict(zip(commits["author_id"], commits["author_name"]))
        selected_authors = st.multiselect("开发者", sorted(author_options), format_func=lambda a: f"{author_options[a]} · {a}", placeholder="全部开发者", key="authors_" + key)
    with module_col:
        selected_modules = st.multiselect("模块（首级目录）", sorted(changes["module"].unique()), placeholder="全部模块", key="modules_" + key)
    st.caption("时间依据：committer date。选择模块后，文件与行数只统计该模块；提交数统计触及该模块的提交。")
if len(selected_dates) != 2:
    st.info("请选择完整的开始日期和结束日期。")
    st.stop()
start, end = selected_dates
if active_sprint:
    for note in coverage_note(meta, commits, start, end):
        st.warning(note)
selected_commits, selected_changes = filter_frames(commits, changes, start, end, selected_authors, selected_modules)
stats = metrics(selected_commits, selected_changes)
for col, label, value in zip(st.columns(5), ["提交", "作者标识", "文件路径", "新增行", "删除行"], [stats["commits"], stats["developers"], stats["files"], stats["added"], stats["deleted"]]):
    col.metric(label, f"{value:,}")
if selected_commits.empty:
    st.info("当前筛选范围没有提交。请调整日期、开发者或模块。")
    st.stop()

overview, developers, explorer, reports = st.tabs(["仓库概览", "开发者活动", "文件与提交", "Sprint 报告"])

with overview:
    left, right = st.columns([1.6, 1])
    daily = daily_activity(selected_commits, selected_changes)
    with left:
        title("提交时间线", "包含没有提交的日期，展示实际开发节奏。")
        fig = px.area(daily, x="date", y="commits", markers=True, labels={"date": "日期", "commits": "提交数"})
        fig.update_traces(line_color=COLORS[0], fillcolor="rgba(8,127,140,.13)")
        fig.update_yaxes(dtick=1 if daily["commits"].max() < 10 else None)
        plot(fig, "timeline")
    with right:
        title("模块变化量", "新增行数 + 删除行数；模块按首级目录划分。")
        modules = module_activity(selected_changes)
        if not modules.empty:
            plot(px.bar(modules.head(10).sort_values("churn"), x="churn", y="module", orientation="h", labels={"churn": "代码变动行数", "module": "模块"}), "modules")
        else:
            st.info("没有文件变更可统计。")
    left, right = st.columns([1.6, 1])
    with left:
        title("代码增删趋势")
        long = daily.melt(id_vars=["date"], value_vars=["added", "deleted"], var_name="类型", value_name="行数")
        long["类型"] = long["类型"].map({"added": "新增", "deleted": "删除"})
        plot(px.bar(long, x="date", y="行数", color="类型", barmode="group", labels={"date": "日期"}, color_discrete_sequence=[COLORS[0], "#d28b6b"]), "lines")
    with right:
        title("修改最频繁的文件", "同一提交内按文件路径去重。")
        top = file_activity(selected_changes).head(8)
        st.dataframe(top[["path", "commits"]].rename(columns={"path": "文件", "commits": "提交次数"}), hide_index=True, width="stretch")

with developers:
    title("开发者活动", "这些指标描述 Git 中的可观察活动，不代表工作质量、工时或课程贡献比例。")
    activity = developer_activity(selected_commits, selected_changes)
    st.dataframe(activity.rename(columns={"author_id": "作者标识", "name": "姓名", "commits": "提交", "files": "文件", "modules": "参与模块", "added": "新增行", "deleted": "删除行"}), hide_index=True, width="stretch")
    stacked = selected_commits.groupby(["date", "author_id"]).size().reset_index(name="commits")
    plot(px.bar(stacked, x="date", y="commits", color="author_id", labels={"date": "日期", "commits": "提交数", "author_id": "开发者"}), "developer_timeline")
    st.caption("默认按小写 email 区分作者；未配置自动别名合并。")

with explorer:
    title("文件变化排行")
    ranking = file_activity(selected_changes)
    st.dataframe(ranking.rename(columns={"path": "文件", "commits": "提交次数", "added": "新增行", "deleted": "删除行", "churn": "变动行数"}), hide_index=True, width="stretch", height=260)
    paths = ranking["path"].tolist()
    file_filter = st.selectbox("按文件浏览提交", ["全部文件", *paths], key="file_" + key)
    explorer_commits = selected_commits
    if file_filter != "全部文件":
        hashes = selected_changes.loc[selected_changes["path"] == file_filter, "commit_hash"]
        explorer_commits = selected_commits[selected_commits["hash"].isin(hashes)]
    explorer_commits = explorer_commits.sort_values("time", ascending=False)
    table = explorer_commits[["hash", "subject", "author_name", "time"]].copy()
    table["hash"] = table["hash"].str[:10]
    table["time"] = table["time"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(table.rename(columns={"hash": "Commit", "subject": "提交说明", "author_name": "作者", "time": "时间"}), hide_index=True, width="stretch")
    options = explorer_commits["hash"].tolist()
    if options:
        subjects = dict(zip(explorer_commits["hash"], explorer_commits["subject"]))
        sha = st.selectbox("选择提交查看 diff", options, format_func=lambda s: f"{s[:10]} · {subjects[s]}", key="commit_" + key)
        display_commit(sha, selected_commits, selected_changes, "explorer")

with reports:
    title("Sprint 回顾报告", "统计由程序计算；AI 可选，用于解释变化。所有内容使用当前筛选范围。")
    report_title = st.text_input("报告名称", value=active_sprint["name"] + " 变化报告" if active_sprint else "Sprint 开发回顾", key="report_title_" + repo_key + sprint_id)
    context = {"title": report_title, "start": str(start), "end": str(end), "timezone": timezone, "authors": selected_authors, "modules": selected_modules}
    if active_sprint:
        context["sprint"] = active_sprint
        context["coverage_warnings"] = coverage_note(meta, commits, start, end)
        st.caption(f"当前 Sprint：{active_sprint['name']} · {active_sprint['start']} 至 {active_sprint['end']} · 报告使用当前分支及作者/模块筛选。")
    scope_key = fingerprint({"run": meta["id"], "context": context, "hashes": selected_commits["hash"].tolist()})
    payload = build_ai_payload(selected_commits, selected_changes)
    payload["scope"] = context
    ai_key = summary_key(payload, base_url, model)
    existing_ai = load_summary(ai_key)
    st.caption(f"AI 输入预览：{len(selected_commits)} 条选中提交，提供 {len(payload['commits'])} 条提交的代码依据；最多每条 8 个文件，diff 按预算截断。作者姓名与 email 不作为独立字段发送。")
    consent = st.checkbox("我同意将当前范围的提交说明、路径和部分 diff 发送至配置的模型接口", key="consent")
    use_cache = st.checkbox("复用相同输入的 AI 摘要缓存", value=True)
    if st.button("生成 AI 摘要", type="primary", disabled=not consent or not model.strip() or not payload["commits"]):
        st.session_state.pop("ai_error_for_" + scope_key, None)
        try:
            with st.spinner("正在生成并校验摘要依据…"):
                result = existing_ai if use_cache and existing_ai else generate_ai_report(payload, base_url, model, api_key)
                if result is not existing_ai:
                    save_summary(ai_key, result)
                st.session_state["ai_for_" + scope_key] = {"key": ai_key, "report": result}
            st.success("摘要已生成；提交与文件引用已校验，文字结论仍需核查。")
        except SummaryError as exc:
            st.session_state["ai_error_for_" + scope_key] = {"key": ai_key, "message": str(exc)}
    stored = st.session_state.get("ai_for_" + scope_key)
    report = stored["report"] if stored and stored["key"] == ai_key else factual_report(selected_commits, selected_changes)
    last_error = st.session_state.get("ai_error_for_" + scope_key)
    last_error = last_error if last_error and last_error["key"] == ai_key else None
    if last_error:
        st.error(last_error["message"])
    if report["mode"] == "factual":
        if last_error:
            report["ai_attempt_failed"] = True
            report["limitations"][0] = "AI 请求或摘要校验未成功；本报告由程序统计生成，未使用失败的模型结果。"
            st.info("本次 AI 生成或引用校验未通过，下面保留程序计算的统计报告。可重新生成；统计和 diff 仍可正常使用。")
        else:
            st.info("当前显示统计报告，未调用 AI。配置模型并勾选发送确认后，可生成智能摘要。")
    else:
        if last_error:
            st.info("本次生成未通过，当前保留上一次成功生成的 AI 摘要。")
        st.caption(f"AI 摘要 · {report['model']} · {report['prompt_version']} · 不是完整代码审查结论")
    st.markdown(f"#### {html.escape(report_title)}")
    st.caption(f"{start} — {end} · {timezone} · {stats['commits']} commits · {stats['developers']} 个作者标识（按邮箱区分）")
    evidence_hashes = set()
    for item in report["highlights"]:
        with st.container(border=True):
            st.text(item["text"])
            for entry in item["evidence"]:
                evidence_hashes.add(entry["commit_hash"])
                st.caption(f"依据 {entry['commit_hash'][:10]} · {', '.join(entry['files'])}")
    if evidence_hashes:
        with st.expander("核查报告依据：查看原始提交与 diff"):
            evidence_sha = st.selectbox("报告引用的提交", sorted(evidence_hashes), format_func=lambda s: s[:12], key="evidence_" + scope_key)
            display_commit(evidence_sha, selected_commits, selected_changes, "evidence")
    with st.expander("报告限制与统计口径"):
        for warning in meta["warnings"] + report["limitations"]:
            st.write("• " + warning)
        if report["mode"] == "ai":
            st.write(f"语义摘要依据覆盖 {report['coverage']['evidence_commits']} / {report['coverage']['selected_commits']} 条提交；文件和 diff 可能截断。引用校验不等同于事实校验。")
    markdown = export_markdown(meta, context, selected_commits, selected_changes, report)
    sprint_filename = re.sub(r"[^\w.-]+", "-", active_sprint["name"])[:60] + "-" if active_sprint else ""
    st.download_button("下载 Markdown 报告", markdown, file_name=f"changeguard-{sprint_filename}{start}-{end}.md", mime="text/markdown", width="stretch", on_click="ignore")
    with st.expander("查看发送给模型的数据结构"):
        st.json(payload, expanded=False)

with st.expander("分析快照与数据边界"):
    st.text(f"仓库：{meta['path']}\n分支：{short_branch(meta['branch'])}\n固定 tip：{meta['tip']}\n采集时间：{meta['created_at']}")
    for warning in meta["warnings"]:
        st.write("• " + warning)
