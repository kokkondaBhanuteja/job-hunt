"""
Diagnostic harness for the Naukri scraper. Run when found=0 to see WHY.

What it does:
  1. Opens a HEADED Chromium so you can see exactly what Naukri serves
  2. Goes to the listing URL we generate
  3. Saves a screenshot + the rendered HTML
  4. Tries multiple known selector variants and reports which (if any) hit
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

from job_hunt.sources.naukri import (
    DEFAULT_SELECTORS,
    SESSION_DIR,
    USER_AGENT,
    VIEWPORT,
    build_search_url,
)

OUT = Path(__file__).resolve().parents[1] / "data" / "logs"
OUT.mkdir(parents=True, exist_ok=True)

CANDIDATE_CARD_SELECTORS = [
    "div.srp-jobtuple-wrapper",
    "div.cust-job-tuple",
    "div.jobTuple",
    "article.jobTuple",
    "div[data-job-id]",
    ".jobTupleHeader",
    "section.list-result",
]


async def main(keyword: str, location: str) -> None:
    url = build_search_url(keyword, location, page=1)
    print(f"URL → {url}")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,                      # <-- visible
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60_000)
        except Exception as exc:
            print(f"navigation error: {exc}")

        # Give the SPA a moment.
        await asyncio.sleep(4)

        title = await page.title()
        cur_url = page.url
        print(f"page title    : {title!r}")
        print(f"current URL   : {cur_url}")

        # Save screenshot + HTML for inspection
        shot = OUT / "naukri-debug.png"
        html = OUT / "naukri-debug.html"
        await page.screenshot(path=str(shot), full_page=True)
        Path(html).write_text(await page.content(), encoding="utf-8")
        print(f"screenshot    : {shot}")
        print(f"html          : {html}")

        # Try every candidate selector
        print("\n-- selector probe --")
        for sel in CANDIDATE_CARD_SELECTORS:
            count = await page.locator(sel).count()
            marker = "✓" if count else "·"
            print(f"  {marker} {sel:<40} → {count}")

        # And what our current DEFAULT_SELECTORS produce
        print("\n-- current defaults --")
        for name, sel in DEFAULT_SELECTORS.items():
            count = await page.locator(sel).count()
            marker = "✓" if count else "·"
            print(f"  {marker} {name:<12} ({sel:<60}) → {count}")

        # Heuristic: scan for high-density text blocks that look like job cards
        print("\n-- looking for 'job' / 'developer' anywhere --")
        anchors = await page.locator("a").all()
        sample = []
        for a in anchors[:30]:
            href = await a.get_attribute("href") or ""
            txt = (await a.inner_text())[:80].strip().replace("\n", " ")
            if "job-listings" in href or "developer" in txt.lower():
                sample.append({"text": txt, "href": href})
        print(json.dumps(sample[:10], indent=2))

        input("\nPress Enter in this terminal to close the browser...")
        await ctx.close()


if __name__ == "__main__":
    import sys

    kw = sys.argv[1] if len(sys.argv) > 1 else "nestjs backend"
    loc = sys.argv[2] if len(sys.argv) > 2 else "bangalore"
    asyncio.run(main(kw, loc))
