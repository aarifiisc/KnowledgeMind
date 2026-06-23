"""Screenshot DB Records tab, then both Demo sections after running them."""
import asyncio
from playwright.async_api import async_playwright

async def click_tab(tabs, label_fragment):
    for t in tabs:
        text = await t.inner_text()
        if label_fragment.lower() in text.lower():
            await t.click()
            return True
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto("http://localhost:7860", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        tabs = await page.query_selector_all("button[role='tab']")
        print(f"Total tabs: {len(tabs)}")
        for i, t in enumerate(tabs):
            txt = await t.inner_text()
            print(f"  {i}: {txt.encode('ascii','replace').decode()!r}")

        # ── DB Records tab ────────────────────────────────────────────────
        await click_tab(tabs, "DB Records")
        await page.wait_for_timeout(1500)

        # Click refresh all tables
        refresh_btn = await page.query_selector("button:text('Refresh all tables')")
        if refresh_btn:
            await refresh_btn.click()
            await page.wait_for_timeout(2000)

        await page.screenshot(path="db_records_tab.png")
        print("Saved db_records_tab.png")

        # Expand all accordions
        accordions = await page.query_selector_all("button.accordion-header, button[aria-expanded]")
        for acc in accordions:
            expanded = await acc.get_attribute("aria-expanded")
            if expanded == "false":
                await acc.click()
                await page.wait_for_timeout(300)
        await page.screenshot(path="db_records_tab_expanded.png")
        print("Saved db_records_tab_expanded.png")

        # ── Demo tab ──────────────────────────────────────────────────────
        tabs = await page.query_selector_all("button[role='tab']")
        await click_tab(tabs, "Demo")
        await page.wait_for_timeout(1500)
        await page.screenshot(path="demo_tab_initial.png")
        print("Saved demo_tab_initial.png")

        # Run query demo
        query_btn = await page.query_selector("button:text('Run Query Demo')")
        if query_btn:
            await query_btn.click()
            await page.wait_for_timeout(5000)
        await page.screenshot(path="demo_tab_query_result.png")
        print("Saved demo_tab_query_result.png")

        # Run preemptive demo
        preemptive_btn = await page.query_selector("button:text('Run Preemptive Demo')")
        if preemptive_btn:
            await preemptive_btn.click()
            await page.wait_for_timeout(5000)
        await page.screenshot(path="demo_tab_preemptive_result.png")
        print("Saved demo_tab_preemptive_result.png")

        await browser.close()

asyncio.run(main())
