"""Run against an already-running RepoLens server; no paid model calls."""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "work" / "browser"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    expect.set_options(timeout=30000)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role("button", name="载入演示仓库", exact=True).wait_for(timeout=60000)
        page.screenshot(path=str(output / "landing.png"), full_page=True)
        page.get_by_role("button", name="载入演示仓库", exact=True).click()
        expect(page.get_by_role("tab", name="仓库概览", exact=True)).to_be_visible(timeout=90000)
        expect(page.get_by_test_id("stMetricValue").nth(0)).to_have_text("18", timeout=60000)
        expect(page.get_by_test_id("stMetricValue").nth(1)).to_have_text("3")
        expect(page.get_by_test_id("stMetricValue").nth(2)).to_have_text("14")
        page.get_by_text("分析快照与数据边界", exact=True).wait_for(state="attached", timeout=60000)
        expect(page.get_by_role("tabpanel", name="仓库概览").get_by_test_id("stPlotlyChart").first).to_be_visible()
        expect(page.get_by_test_id("stException")).to_have_count(0)
        page.mouse.move(1300, 600)
        page.screenshot(path=str(output / "overview.png"), full_page=True)
        print("Verified overview", flush=True)

        page.get_by_role("tab", name="开发者活动", exact=True).click()
        expect(page.get_by_role("tabpanel", name="开发者活动").get_by_test_id("stDataFrame")).to_be_visible()
        page.get_by_role("tab", name="文件与提交", exact=True).click()
        explorer = page.get_by_role("tabpanel", name="文件与提交")
        expect(explorer.get_by_role("combobox", name="选择提交查看 diff")).to_be_visible()
        expander = explorer.get_by_test_id("stExpander").filter(has_text="src/reports/export.py")
        expander.locator("summary").click()
        expect(expander.get_by_test_id("stCode")).to_be_visible()
        expect(expander.get_by_test_id("stCode")).to_contain_text("def to_markdown")
        page.screenshot(path=str(output / "diff.png"), full_page=True)
        print("Verified developer table and diff", flush=True)

        page.get_by_role("tab", name="变化报告", exact=True).click()
        report_panel = page.get_by_role("tabpanel", name="变化报告")
        expect(report_panel.get_by_text("当前显示统计报告，未调用 AI。", exact=False)).to_be_visible()
        with page.expect_download() as download_event:
            report_panel.get_by_role("button", name="下载 Markdown 报告").click()
        download = download_event.value
        target = output / download.suggested_filename
        download.save_as(target)
        report = target.read_text(encoding="utf-8")
        assert "统计报告（未调用 AI）" in report
        assert "提交 18" in report
        print("Verified report download", flush=True)

        page.get_by_test_id("stMain").evaluate("el => el.scrollTo({top: 0, behavior: 'instant'})")
        author_input = page.get_by_role("combobox", name="开发者", exact=True)
        author_input.fill("Bob")
        page.get_by_role("option", name="Bob · bob@example.test", exact=True).click()
        page.keyboard.press("Escape")
        expect(page.get_by_test_id("stMetricValue").nth(0)).to_have_text("5", timeout=30000)
        expect(page.get_by_test_id("stMetricValue").nth(1)).to_have_text("1")
        expect(page.get_by_test_id("stException")).to_have_count(0)
        print("Verified author filter", flush=True)

        page.get_by_role("combobox", name="模块（首级目录）", exact=True).fill("docs")
        page.get_by_role("option", name="docs", exact=True).click()
        page.keyboard.press("Escape")
        expect(page.get_by_text("当前筛选范围没有提交。", exact=False)).to_be_visible(timeout=30000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        assert not errors, errors
        browser.close()
    print("Browser smoke passed: demo, charts, developer tab, diff, Markdown download, author/module filtering, empty state.")


if __name__ == "__main__":
    main()
