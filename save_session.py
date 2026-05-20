"""
Run this once to save your Vinted login session.

    source .venv/bin/activate
    python save_session.py

A Chromium window will open. Log in to vinted.cz normally, then come back
here and press Enter. Your session (cookies + localStorage) is saved to
browser_session.json and the scraper will use it automatically.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = "browser_session.json"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.vinted.cz")

        print()
        print("=" * 55)
        print("  Chromium is open.  Log in to Vinted.cz normally.")
        print("  When you're fully logged in, come back here and")
        print("  press Enter to save the session.")
        print("=" * 55)
        input("\n  Press Enter when logged in... ")

        await context.storage_state(path=SESSION_FILE)
        await browser.close()

    size_kb = Path(SESSION_FILE).stat().st_size // 1024
    print(f"\n  Session saved → {SESSION_FILE}  ({size_kb} KB)")
    print("  The scraper will use it automatically on the next run.\n")


if __name__ == "__main__":
    asyncio.run(main())
