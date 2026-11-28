"""Sprint comparison view, kept separate from mining and report generation."""

import plotly.express as px
import streamlit as st

from repolens.comparison import activity_table, compare_sprints, export_comparison, metric_table


def render_comparison(meta, commits, changes, sprints, authors, modules, timezone, repo_key, plot):
    st.subheader("Sprint 对比")
    st.caption("分别选择 A（基准）与 B（对照）。两期使用当前分支快照及相同的开发者、模块筛选，日期独立于上方单期选择。无需配置 AI。")
    if len(sprints) < 2:
        st.info("请先在「Sprint 工作区」创建至少两个 Sprint，再进行对比。")
        return
    mapping = {sprint["id"]: sprint for sprint in sprints}
    options = list(mapping)
    left, right = st.columns(2)
    selections = []
    for label, col, default in (("A", left, 0), ("B", right, 1)):
        widget_key = "compare_" + label + repo_key
        if st.session_state.get(widget_key) not in mapping:
            st.session_state[widget_key] = options[default]
        with col:
            chosen = st.selectbox("对比 Sprint " + label, options, key=widget_key,
                                  format_func=lambda item: mapping[item]["name"])
            sprint = mapping[chosen]
            st.caption(f"{sprint['start']} 至 {sprint['end']}（含首尾）")
            selections.append(sprint)
    if selections[0]["id"] == selections[1]["id"]:
        st.info("请选择两个不同的 Sprint。")
        return
    result = compare_sprints(meta, commits, changes, *selections, authors, modules)
    st.caption(f"时区：{timezone} · 开发者筛选：{', '.join(authors) or '全部'} · 模块筛选：{', '.join(modules) or '全部'}")
    for warning in result["warnings"]:
        st.warning(warning)
    st.dataframe(metric_table(result), hide_index=True, width="stretch")
    st.caption("差值与变化率为 B 相对 A；A 为 0 时变化率无定义。提交量和行数描述活动，不代表质量或个人贡献比例。")
    st.markdown("#### 模块变化对比")
    table = result["modules"]
    if table.empty:
        st.info("两期在当前筛选条件下均无文件变更。")
    else:
        chart = table.head(12)[["module", "churn_a", "churn_b"]].rename(
            columns={"churn_a": "A", "churn_b": "B"}
        ).melt(id_vars="module", var_name="Sprint", value_name="变动行数")
        plot(px.bar(chart, x="module", y="变动行数", color="Sprint", barmode="group",
                    labels={"module": "模块"}), "sprint_comparison_modules")
        st.caption("图表展示两期合计变动量最高的 12 个模块；表格包含全部模块。变动行数 = 新增行 + 删除行。")
        st.dataframe(activity_table(table), hide_index=True, width="stretch")
    st.markdown("#### 文件变化对比")
    st.caption("仅 A/B 有变更表示该路径只在相应期间被修改，不代表文件新增或删除；路径重命名前后分别计数。")
    files = result["files"]
    if not files.empty:
        st.dataframe(activity_table(files), hide_index=True, width="stretch")
    st.download_button("下载 Sprint 对比报告", export_comparison(meta, result, timezone),
                       file_name=f"changeguard-sprint-comparison-A-{selections[0]['start']}-{selections[0]['end']}-B-{selections[1]['start']}-{selections[1]['end']}.md",
                       mime="text/markdown", width="stretch", on_click="ignore")
