from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.async_api import Browser, Page, async_playwright

_playwright = None
_browser: Browser | None = None
_page: Page | None = None


async def open_browser(url: str = "about:blank") -> dict:
    global _playwright, _browser, _page
    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None:
        _browser = await _playwright.chromium.launch(headless=False)
    _page = await _browser.new_page()
    await _page.goto(url)
    return {"opened": True, "url": url}


async def navigate(url: str) -> dict:
    page = await _ensure_page()
    if "://" not in url and not url.startswith("about:"):
        url = "https://" + url
    await page.goto(url)
    return {"url": page.url}


async def click_element(selector: str) -> dict:
    page = await _ensure_page()
    await page.click(selector)
    return {"clicked": selector}


async def fill_form(selector: str, value: str) -> dict:
    page = await _ensure_page()
    await page.fill(selector, value)
    return {"selector": selector, "filled": True}


async def get_page_text() -> str:
    page = await _ensure_page()
    return await page.locator("body").inner_text(timeout=5000)


async def take_page_screenshot() -> str:
    page = await _ensure_page()
    path = Path(tempfile.mktemp(prefix="jarvis_page_", suffix=".png"))
    await page.screenshot(path=str(path), full_page=True)
    return str(path)


async def close_browser() -> dict:
    global _playwright, _browser, _page
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    _browser = None
    _page = None
    _playwright = None
    return {"closed": True}


async def _ensure_page() -> Page:
    global _page
    if _page is None:
        await open_browser()
    assert _page is not None
    return _page
