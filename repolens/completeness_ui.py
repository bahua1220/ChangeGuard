"""UI for bounded, evidence-backed missing-change suggestions."""

import pandas as pd
import streamlit as st

from repolens.analytics import frames
from repolens.completeness import CheckOptions, DETECTOR_VERSION, STATUS_TEXT, export_completeness, review_commit
from repolens.mining import RepositoryError
from repolens.reports import fingerprint


def render_completeness(snapshot, selected_commits, display_commit):
    st.subheader("潜在遗漏修改检查")
    st.caption("选择一个提交，检查是否有历史上经常一起修改、此次却未修改的文件。无需 AI；结果用于提示人工检查。")
    if selected_commits.empty:
        st.info("当前筛选范围没有可检查的目标提交，请调整上方筛选。")
        return
    meta = snapshot["meta"]
    targets = selected_commits.sort_values(["time", "hash"], ascending=False)
    choices = targets["hash"].tolist()
    subjects = dict(zip(targets["hash"], targets["subject"]))
    default = next((i for i, sha in enumerate(choices) if subjects[sha].startswith("demo: auth-only change")), 0) if meta["name"] == "completeness_demo_repository" else 0
    sha = st.selectbox("选择待检查提交", choices, index=default,
                       format_func=lambda item: item[:10] + " · " + subjects[item], key="completeness_target_" + meta["id"])
    with st.expander("检测范围与阈值", expanded=True):
        left, right = st.columns(2)
        with left:
            limit = st.number_input("历史窗口上限（已采集祖先）", 1, 2000, 500, 50)
            support = st.number_input("最少共同修改次数", 2, 100, 3, 1)
        with right:
            confidence = st.slider("最低历史关联比例（%）", 1, 100, 60, 5)
            max_files = st.number_input("每提交最多涉及路径", 2, 100, 20, 1)
        st.caption("目标列表使用上方筛选；历史学习使用同一快照内已采集的祖先提交，不受日期、作者、模块筛选限制。只检查小规模、稳定路径的文本 MODIFY。")
    options = CheckOptions(int(limit), int(support), confidence / 100, int(max_files))
    scope = fingerprint({"run": meta["id"], "target": sha, "options": options.__dict__, "version": DETECTOR_VERSION})
    if st.button("检查潜在遗漏", type="primary"):
        try:
            with st.spinner("正在读取祖先历史并匹配共同修改规则…"):
                result = review_commit(snapshot, sha, options)
            st.session_state["completeness_result"] = {"scope": scope, "result": result}
        except (RepositoryError, ValueError) as exc:
            st.session_state.pop("completeness_result", None)
            st.error(str(exc))
    saved = st.session_state.get("completeness_result")
    if not saved or saved["scope"] != scope:
        st.info("选择提交后点击「检查潜在遗漏」。可用左侧「载入遗漏检测演示」体验有建议和无建议的案例。")
        return
    result = saved["result"]
    st.caption(f"目标 {sha[:12]} · 已采集祖先 {result['history_considered']} 条 · 有效历史事务 {result['history_used']} 条 · {DETECTOR_VERSION}")
    for note in result["warnings"]:
        st.warning(note)
    if result["candidates"]:
        st.warning("发现潜在遗漏检查建议；历史相关性不等于本次必须修改。")
        rows = [{"建议检查文件": item["path"], "触发文件": item["rules"][0]["trigger"],
                 "共同修改次数": item["rules"][0]["support"], "触发文件修改次数": item["rules"][0]["trigger_count"],
                 "历史关联比例": f"{item['rules'][0]['confidence']:.1%}"} for item in result["candidates"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        for index, candidate in enumerate(result["candidates"]):
            with st.expander("建议检查：" + candidate["path"], expanded=index == 0):
                for rule in candidate["rules"]:
                    st.text(f"修改 {rule['trigger']} 的 {rule['trigger_count']} 条有效历史提交中，{rule['support']} 条也修改 {candidate['path']}（{rule['confidence']:.1%}）。本次未触及该候选。")
                    st.caption("共同修改依据：" + ", ".join(item[:12] for item in rule["evidence_hashes"]))
        if result["candidate_count"] > len(result["candidates"]):
            st.caption(f"共 {result['candidate_count']} 个候选，按关联比例和共同修改次数展示前 {len(result['candidates'])} 个。")
    else:
        st.info(STATUS_TEXT[result["status"]])
    all_commits, all_changes = frames(snapshot)
    evidence = list(dict.fromkeys(sha for item in result["candidates"] for rule in item["rules"] for sha in rule["evidence_hashes"]))
    if evidence:
        with st.expander("查看共同修改的原始提交与 diff"):
            evidence_sha = st.selectbox("遗漏检查引用的历史提交", evidence, format_func=lambda item: item[:12])
            display_commit(evidence_sha, all_commits, all_changes, "completeness_evidence")
    with st.expander("当前提交文件与检测口径"):
        st.write("本次完整触及路径：")
        for path in result["target_paths"]:
            st.text(path)
        st.write("有效触发路径及历史次数：", result["seed_counts"])
        st.write("跳过的历史事务：", result["skipped"])
        st.caption(f"窗口内 {len(result['unstable_paths'])} 个重命名/删除路径不参与学习；候选要求在目标提交中仍存在。关联比例不是缺陷概率，未发现候选也不证明完整性。")
    st.download_button("下载遗漏检查报告", export_completeness(meta, result),
                       file_name=f"changeguard-completeness-{sha[:12]}.md", mime="text/markdown", on_click="ignore", width="stretch")
