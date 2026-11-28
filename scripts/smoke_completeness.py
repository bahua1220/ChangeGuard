"""Browser acceptance of actual suggestions, evidence, controls and export."""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "work/browser"
    output.mkdir(parents=True, exist_ok=True)
    expect.set_options(timeout=30000)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1500})
        page.goto(args.url)
        page.get_by_role("button", name="载入遗漏检测演示", exact=True).click(timeout=60000)
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("15", timeout=90000)
        page.get_by_role("tab", name="遗漏修改检查", exact=True).click()
        panel = page.get_by_role("tabpanel", name="遗漏修改检查")
        target = panel.get_by_role("combobox", name="选择待检查提交", exact=True)
        expect(target).to_have_value(__import__("re").compile(".*auth-only change.*"))
        panel.get_by_role("button", name="检查潜在遗漏", exact=True).click()
        expect(panel.get_by_text("发现潜在遗漏检查建议；历史相关性不等于本次必须修改。", exact=True)).to_be_visible()
        expect(panel.get_by_test_id("stDataFrame")).to_have_count(1)
        expect(panel.get_by_text("建议检查：tests/test_auth.py", exact=True)).to_be_visible()
        expect(panel.get_by_text("修改 src/auth.py 的 4 条有效历史提交中，4 条也修改 tests/test_auth.py（100.0%）。本次未触及该候选。", exact=True)).to_be_visible()
        with page.expect_download() as event:
            panel.get_by_role("button", name="下载遗漏检查报告", exact=True).click()
        download = event.value
        report = output / download.suggested_filename
        download.save_as(report)
        text = report.read_text(encoding="utf-8")
        assert "tests/test_auth.py" in text and "100.0%" in text and "不是缺陷概率" in text
        panel.get_by_text("查看共同修改的原始提交与 diff", exact=True).click()
        expect(panel.get_by_role("combobox", name="遗漏检查引用的历史提交", exact=True)).to_be_visible()
        expect(panel.get_by_text("MODIFY · src/auth.py", exact=False).first).to_be_visible()
        panel.get_by_role("heading", name="潜在遗漏修改检查", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(output / "completeness.png"), full_page=True)

        def choose(phrase):
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo({top:0, behavior:'instant'})")
            target.click()
            target.press("ArrowDown")
            target.fill(phrase)
            page.get_by_role("option").filter(has_text=phrase).click()
            expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
            panel.get_by_role("button", name="检查潜在遗漏", exact=True).click()

        choose("complete auth and test")
        expect(panel.get_by_text("当前历史窗口与阈值下未发现候选文件；这不代表该提交已经完整。", exact=True)).to_be_visible()
        choose("unrelated cache-only")
        expect(panel.get_by_text("当前历史窗口与阈值下未发现候选文件；这不代表该提交已经完整。", exact=True)).to_be_visible()
        expect(page.get_by_test_id("stException")).to_have_count(0)
        browser.close()
    print("Completeness browser acceptance passed: positive suggestion, historical evidence, Markdown export, complete/unrelated controls.")


if __name__ == "__main__":
    main()
