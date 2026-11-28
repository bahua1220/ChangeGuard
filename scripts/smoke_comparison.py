"""Browser acceptance for independent Sprint comparison, filters and export."""

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
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.goto(args.url)
        page.get_by_role("button", name="载入演示仓库", exact=True).click(timeout=60000)
        expect(page.get_by_test_id("stMetricValue").first).to_have_text("18", timeout=90000)
        page.get_by_role("tab", name="Sprint 对比", exact=True).click()
        panel = page.get_by_role("tabpanel", name="Sprint 对比")
        a = panel.get_by_role("combobox", name="对比 Sprint A", exact=True)
        b = panel.get_by_role("combobox", name="对比 Sprint B", exact=True)

        def choose(widget, name):
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo({top:0, behavior:'instant'})")
            widget.click()
            widget.press("ArrowDown")
            widget.fill(name)
            option = page.get_by_role("option", name=name, exact=True)
            try:
                option.click(timeout=10000)
            except Exception:
                page.screenshot(path=str(output / "comparison-selection-failure.png"), full_page=True)
                (output / "comparison-selection-failure.txt").write_text(page.locator("body").aria_snapshot(), encoding="utf-8")
                raise
            expect(widget).to_have_value(name)
            expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")

        # Existing local data may contain additional user-created Sprint ranges.
        choose(a, "Sprint 1")
        choose(b, "Sprint 2")
        expect(panel.get_by_test_id("stPlotlyChart")).to_have_count(1)
        expect(panel.get_by_test_id("stDataFrame")).to_have_count(3)
        expect(panel.get_by_text("两个 Sprint 时长不同；总量比较请结合平均每日提交数查看。", exact=True)).to_be_visible()

        def download_report():
            with page.expect_download() as event:
                panel.get_by_role("button", name="下载 Sprint 对比报告", exact=True).click()
            download = event.value
            path = output / download.suggested_filename
            download.save_as(path)
            return path.read_text(encoding="utf-8")

        report = download_report()
        assert "| 提交数 | 9 | 9 | 0 | +0.0% |" in report
        assert "| 新增行 | 38 | 24 | -14 | -36.8% |" in report
        assert "A：Sprint 1" in report and "B：Sprint 2" in report
        assert "src/mining/extractor.py" in report and "未调用 AI" in report
        panel.get_by_role("heading", name="Sprint 对比", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(output / "sprint-comparison-all-authors.png"), full_page=True)

        choose(b, "Sprint 1")
        expect(panel.get_by_text("请选择两个不同的 Sprint。", exact=True)).to_be_visible()
        expect(panel.get_by_role("button", name="下载 Sprint 对比报告", exact=True)).to_have_count(0)
        choose(a, "Sprint 2")
        expect(panel.get_by_role("button", name="下载 Sprint 对比报告", exact=True)).to_be_visible()
        report = download_report()
        assert "| 新增行 | 24 | 38 | 14 | +58.3% |" in report

        # Restore chronological order and apply an author filter to both sides.
        choose(b, "Sprint 2")
        expect(panel.get_by_text("请选择两个不同的 Sprint。", exact=True)).to_be_visible()
        choose(a, "Sprint 1")
        expect(panel.get_by_role("button", name="下载 Sprint 对比报告", exact=True)).to_be_visible()
        authors = page.get_by_role("combobox", name="开发者", exact=True)
        authors.fill("Bob")
        page.get_by_role("option", name="Bob · bob@example.test", exact=True).click()
        page.keyboard.press("Escape")
        expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
        expect(panel.get_by_text("时区：Asia/Shanghai · 开发者筛选：bob@example.test · 模块筛选：全部", exact=True)).to_be_visible()
        report = download_report()
        assert "| 提交数 | 3 | 2 | -1 | -33.3% |" in report
        assert "作者筛选：bob@example.test" in report
        assert "src/storage/cache.py" not in report
        expect(page.get_by_test_id("stException")).to_have_count(0)
        panel.screenshot(path=str(output / "sprint-comparison.png"))
        browser.close()
    print("Sprint comparison browser acceptance passed: charts, exact totals, swap, same range, author filter, Markdown download.")


if __name__ == "__main__":
    main()
