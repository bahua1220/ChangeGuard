from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_github_entry_and_invalid_page_url_have_actionable_error():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert next(widget for widget in app.radio if widget.label == "仓库来源").value == "GitHub 链接"
    url = next(widget for widget in app.text_input if widget.label == "GitHub 仓库链接")
    url.set_value("https://github.com/ishepard/pydriller/tree/master")
    next(widget for widget in app.button if widget.label == "下载并分析").click().run()
    assert not app.exception
    assert any("仓库首页链接" in error.value for error in app.error)


def test_rejected_ai_output_keeps_factual_report_without_claiming_no_call(monkeypatch, snapshot):
    from repolens import reports

    def reject(*args, **kwargs):
        raise reports.CitationError("第 1 条摘要使用了无效的依据编号，结果未保存。")

    monkeypatch.setattr(reports, "generate_ai_report", reject)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["snapshot"] = snapshot
    app.run()
    next(widget for widget in app.text_input if widget.label == "模型名称").set_value("fixture-model")
    next(widget for widget in app.checkbox if widget.label.startswith("我同意将")).check()
    next(widget for widget in app.checkbox if widget.label == "复用相同输入的 AI 摘要缓存").uncheck()
    app.run()
    next(widget for widget in app.button if widget.label == "生成 AI 摘要").click().run()
    assert not app.exception
    assert any("依据编号" in item.value for item in app.error)
    assert any("保留程序计算的统计报告" in item.value for item in app.info)
    assert not any("未调用 AI" in item.value for item in app.info)
