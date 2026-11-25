"""Exercise saved Sprint selection, per-sprint reports and method details."""

import argparse
from uuid import uuid4
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()
    temporary_name = "验收 Sprint " + uuid4().hex[:6]
    output = Path(__file__).resolve().parents[1] / "work/browser"
    output.mkdir(parents=True, exist_ok=True)
    expect.set_options(timeout=30000)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(args.url)
        page.get_by_role("button", name="载入演示仓库", exact=True).click(timeout=60000)
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("18", timeout=90000)
        page.get_by_text("分析快照与数据边界", exact=True).wait_for(state="attached", timeout=60000)
        selector = page.get_by_role("combobox", name="选择 Sprint", exact=True)
        selector.click()
        page.get_by_role("option", name="Sprint 1", exact=True).click()
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("9")
        page.get_by_role("tab", name="Sprint 报告", exact=True).click()
        panel = page.get_by_role("tabpanel", name="Sprint 报告")
        expect(panel.get_by_role("textbox", name="报告名称", exact=True)).to_have_value("Sprint 1 变化报告")
        with page.expect_download() as event:
            panel.get_by_role("button", name="下载 Markdown 报告", exact=True).click()
        download = event.value
        filename = output / download.suggested_filename
        download.save_as(filename)
        text = filename.read_text(encoding="utf-8")
        assert "Sprint：Sprint 1" in text and "提交 9" in text and "Changed methods" in text
        assert "read_metadata" in text
        assert "src/reports/export.py" not in text
        page.get_by_test_id("stMain").evaluate("el => el.scrollTo({top:0, behavior:'instant'})")
        selector.click()
        page.get_by_role("option", name="Sprint 2", exact=True).click()
        expect(panel.get_by_role("textbox", name="报告名称", exact=True)).to_have_value("Sprint 2 变化报告")
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("9")
        page.get_by_role("tab", name="文件与提交", exact=True).click()
        files = page.get_by_role("tabpanel", name="文件与提交")
        method_file = files.get_by_test_id("stExpander").filter(has_text="src/reports/export.py")
        method_file.locator("summary").click()
        expect(method_file.get_by_test_id("stDataFrame")).to_be_visible()
        expect(method_file.get_by_text("Changed methods · 变更方法", exact=True)).to_be_visible()
        page.get_by_test_id("stMain").evaluate("el => el.scrollTo({top:0, behavior:'instant'})")
        page.get_by_test_id("stExpander").filter(has_text="创建或编辑 Sprint").locator("summary").click()
        page.get_by_role("textbox", name="Sprint 名称", exact=True).fill(temporary_name)
        page.get_by_role("button", name="保存 Sprint", exact=True).click()
        expect(page.get_by_role("combobox", name="选择 Sprint", exact=True)).to_have_value(temporary_name)
        # A new browser session can recover the persisted Sprint definitions.
        another = browser.new_page()
        another.goto(args.url)
        another.get_by_role("button", name="载入演示仓库", exact=True).click(timeout=60000)
        another.get_by_role("combobox", name="选择 Sprint", exact=True).click(timeout=90000)
        expect(another.get_by_role("option", name=temporary_name, exact=True)).to_be_visible()
        page.get_by_role("combobox", name="编辑目标", exact=True).click()
        page.get_by_role("option", name=temporary_name, exact=True).click()
        page.get_by_role("button", name="删除该 Sprint", exact=True).wait_for(timeout=30000)
        page.get_by_role("textbox", name="Sprint 名称", exact=True).fill(temporary_name + " edited")
        page.get_by_role("button", name="保存 Sprint", exact=True).click()
        expect(page.get_by_role("combobox", name="选择 Sprint", exact=True)).to_have_value(temporary_name + " edited")
        page.get_by_role("button", name="删除该 Sprint", exact=True).click()
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("18")
        expect(page.get_by_test_id("stException")).to_have_count(0)
        expect(another.get_by_test_id("stException")).to_have_count(0)
        page.screenshot(path=str(output / "sprints.png"), full_page=True)
        browser.close()
    print("Sprint browser acceptance passed: saved ranges, independent reports, methods, persistence.")


if __name__ == "__main__":
    main()
