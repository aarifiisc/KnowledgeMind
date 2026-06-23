"""Take a screenshot of the Connectors tab in the KnowledgeMind Gradio UI."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        await page.goto("http://localhost:7860", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Find and click the Connectors tab (5th tab, index 4)
        tabs = await page.query_selector_all("button[role='tab']")
        print(f"Found {len(tabs)} tabs")
        for i, tab in enumerate(tabs):
            text = await tab.inner_text()
            safe = text.strip().encode('ascii', 'replace').decode('ascii')
            print(f"  Tab {i}: {safe!r}")

        # Click the Connectors tab
        connector_tab = None
        for tab in tabs:
            text = await tab.inner_text()
            if "Connector" in text or "🔌" in text:
                connector_tab = tab
                break

        if connector_tab is None and len(tabs) >= 5:
            connector_tab = tabs[4]

        if connector_tab:
            await connector_tab.click()
            await page.wait_for_timeout(1500)
            print("Clicked connectors tab")

        await page.screenshot(path="connectors_tab.png", full_page=False)
        print("Screenshot saved to connectors_tab.png")

        # Also try to click the refresh all button
        try:
            refresh_btn = await page.query_selector("button:has-text('Refresh all')")
            if refresh_btn:
                await refresh_btn.click()
                await page.wait_for_timeout(3000)
                await page.screenshot(path="connectors_tab_refreshed.png", full_page=False)
                print("Screenshot after refresh saved to connectors_tab_refreshed.png")
        except Exception as e:
            print(f"Could not click refresh: {e}")

        await browser.close()

asyncio.run(main())
