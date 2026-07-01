"""`hunt login <site>` — one-time interactive login that persists cookies.

RPA pattern: open the site in a real Chromium window (via the Browser Manager's
managed persistent profile), wait for you to sign in, close when you're done.
The profile keeps session cookies / localStorage for weeks; later crawls reuse it
and appear (correctly) as your logged-in self.
"""
from __future__ import annotations

import asyncio

from job_hunt.browser import managed_context, session_dir

SITES: dict[str, dict[str, str]] = {
    "naukri": {
        "url": "https://www.naukri.com/nlogin/login",
        "what_to_do": "Sign in with your Naukri credentials, then close this browser.",
    },
    "foundit": {
        "url": "https://www.foundit.in/seeker/login",
        "what_to_do": "Sign in with your Foundit credentials, then close this browser.",
    },
}


async def _interactive_login(site: str) -> int:
    cfg = SITES.get(site)
    if cfg is None:
        print(f"!! Unknown site '{site}'. Known: {list(SITES)}")
        return 1

    print(f"\n[{site}] opening login page...")
    print(f"        → {cfg['url']}")
    print(f"        {cfg['what_to_do']}")
    print("        (the toolkit waits — close the browser window when done)\n")

    async with managed_context(site, headless=False) as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:  # noqa: BLE001
            print(f"   navigation note: {exc} (continuing — finish login anyway)")

        # Wait until the user closes the window (the context's last page goes away).
        try:
            while ctx.pages:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

    print(f"\n[{site}] session saved to {session_dir(site)}")
    return 0


def login_sync(site: str) -> int:
    return asyncio.run(_interactive_login(site))
