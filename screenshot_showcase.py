"""Full showcase screenshots of all new tabs."""
import asyncio
from playwright.async_api import async_playwright


async def go_tab(page, fragment):
    tabs = await page.query_selector_all("button[role='tab']")
    for t in tabs:
        text = await t.inner_text()
        if fragment.lower() in text.lower():
            await t.click()
            await page.wait_for_timeout(1500)
            return True
    return False


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 860})
        await page.goto("http://localhost:7860", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # ── 1. DB Records — overview (connector_runs open) ────────────────
        await go_tab(page, "DB Records")
        await page.wait_for_timeout(800)
        await page.screenshot(path="shot_db_overview.png")
        print("shot_db_overview.png")

        # Refresh all tables so counts are fresh
        btn = await page.query_selector("button:text('Refresh all tables')")
        if btn:
            await btn.click()
            await page.wait_for_timeout(2500)

        # Open strava_snapshots accordion
        accordions = await page.query_selector_all("button[aria-expanded='false']")
        for acc in accordions:
            text = await acc.inner_text()
            if "strava_snapshots" in text.lower():
                await acc.click()
                await page.wait_for_timeout(600)
                break
        await page.screenshot(path="shot_db_strava.png")
        print("shot_db_strava.png")

        # Open apple_health accordion
        accordions = await page.query_selector_all("button[aria-expanded='false']")
        for acc in accordions:
            text = await acc.inner_text()
            if "apple_health" in text.lower():
                await acc.click()
                await page.wait_for_timeout(600)
                break
        await page.screenshot(path="shot_db_health.png")
        print("shot_db_health.png")

        # Open todoist accordion
        accordions = await page.query_selector_all("button[aria-expanded='false']")
        for acc in accordions:
            text = await acc.inner_text()
            if "todoist" in text.lower():
                await acc.click()
                await page.wait_for_timeout(600)
                break
        await page.screenshot(path="shot_db_todoist.png")
        print("shot_db_todoist.png")

        # ── 2. Demo tab — Query Mode with LOCAL query ─────────────────────
        await go_tab(page, "Demo")
        await page.wait_for_timeout(800)

        # Select "What tasks are overdue?" (LOCAL, personal)
        dropdown = await page.query_selector("select, .wrap > div input[role='combobox']")
        # Use label click approach
        dd = await page.query_selector(".block:has(label:text('Preset queries')) input")
        if not dd:
            dd = await page.query_selector("input[aria-label*='Preset']")

        # Fill query textbox with a LOCAL query (target visible textarea in Demo tab)
        await page.get_by_label("Query (edit or type your own)").fill("What tasks are overdue?")

        qbtn = await page.query_selector("button:text('Run Query Demo')")
        if qbtn:
            await qbtn.click()
            await page.wait_for_timeout(4000)
        await page.screenshot(path="shot_demo_query_local.png")
        print("shot_demo_query_local.png")

        # ── 3. Demo tab — Query Mode with CLOUD query ─────────────────────
        await page.get_by_label("Query (edit or type your own)").fill("Research recent LLM papers and summarize findings")

        qbtn = await page.query_selector("button:text('Run Query Demo')")
        if qbtn:
            await qbtn.click()
            await page.wait_for_timeout(4000)
        await page.screenshot(path="shot_demo_query_cloud.png")
        print("shot_demo_query_cloud.png")

        # ── 4. Demo tab — Preemptive Mode ─────────────────────────────────
        pbtn = await page.query_selector("button:text('Run Preemptive Demo')")
        if pbtn:
            await pbtn.click()
            await page.wait_for_timeout(5000)
        await page.screenshot(path="shot_demo_preemptive.png")
        print("shot_demo_preemptive.png")

        # Scroll down to see full preemptive output
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)
        await page.screenshot(path="shot_demo_preemptive_bottom.png")
        print("shot_demo_preemptive_bottom.png")

        # ── 5. DB Records — verify nudge was written ──────────────────────
        await go_tab(page, "DB Records")
        await page.wait_for_timeout(800)
        btn = await page.query_selector("button:text('Refresh all tables')")
        if btn:
            await btn.click()
            await page.wait_for_timeout(2500)
        # Open preemptive_nudges accordion
        accordions = await page.query_selector_all("button[aria-expanded='false']")
        for acc in accordions:
            text = await acc.inner_text()
            if "nudge" in text.lower():
                await acc.click()
                await page.wait_for_timeout(800)
                break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(500)
        await page.screenshot(path="shot_db_nudges.png")
        print("shot_db_nudges.png")

        await browser.close()

asyncio.run(main())
