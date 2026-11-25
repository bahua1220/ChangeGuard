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
