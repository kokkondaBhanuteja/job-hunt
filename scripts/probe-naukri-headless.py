"""Headless probe of Naukri — dumps title, URL, and selector hit-counts."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from job_hunt.sources.naukri import (
    DEFAULT_SELECTORS,
    SESSION_DIR,
    USER_AGENT,
    VIEWPORT,
    build_search_url,
)

CANDIDATES = [
    "div.srp-jobtuple-wrapper",
    "div.cust-job-tuple",
    "div.jobTuple",
    "div[data-job-id]",
    "article",
    "section.list-result",
    "div.list",
    "a[href*='/job-listings-']",
    "a[title]",
]


async def main(keyword: str, location: str) -> None:
    url = build_search_url(keyword, location, page=1)
    print(json.dumps({"requested_url": url}))

    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=True,
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(4)  # let SPA render
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(2)
        except Exception as exc:
            print(json.dumps({"navigation_error": str(exc)}))

        out = {
            "title": await page.title(),
            "current_url": page.url,
            "selector_hits": {},
        }
        for sel in CANDIDATES:
            try:
                out["selector_hits"][sel] = await page.locator(sel).count()
            except Exception as exc:
                out["selector_hits"][sel] = f"err: {exc}"
        for name, sel in DEFAULT_SELECTORS.items():
            out["selector_hits"][f"default:{name}"] = await page.locator(sel).count()

        # First 5 anchor hrefs that look like job listings
        out["job_anchors"] = []
        anchors = await page.locator("a[href*='job-listings']").all()
        for a in anchors[:5]:
            href = await a.get_attribute("href")
            txt = (await a.inner_text())[:60].strip().replace("\n", " ")
            out["job_anchors"].append({"text": txt, "href": href})

        print(json.dumps(out, indent=2))
        await ctx.close()


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "nestjs backend"
    loc = sys.argv[2] if len(sys.argv) > 2 else "bangalore"
    asyncio.run(main(kw, loc))
