"""Optional live-network acceptance check for the GitHub input workflow."""

import argparse
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--repository", default="https://github.com/octocat/Hello-World")
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "work" / "browser"
    output.mkdir(parents=True, exist_ok=True)
    expect.set_options(timeout=30000)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(args.url)
        page.get_by_role("textbox", name="GitHub 仓库链接", exact=True).fill(args.repository, timeout=60000)
        depth = page.get_by_role("spinbutton", name="下载历史深度", exact=True)
        depth.fill(str(args.depth))
        page.get_by_role("button", name="下载并分析", exact=True).click()
        page.get_by_role("tab", name="仓库概览", exact=True).wait_for(timeout=180000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        expect(page.get_by_text("GitHub 来源：" + args.repository, exact=True)).to_be_visible()
        first_count = page.get_by_test_id("stMetricValue").first
        expect(first_count).to_have_text(re.compile(r"[1-9][0-9,]*"))
        page.get_by_text("分析快照与数据边界", exact=True).wait_for(state="attached", timeout=60000)
        page.mouse.move(1300, 600)
        page.screenshot(path=str(output / "github.png"), full_page=True)
        print("GitHub browser acceptance passed:", args.repository, first_count.inner_text(), "analyzable commits")
        browser.close()


if __name__ == "__main__":
    main()
