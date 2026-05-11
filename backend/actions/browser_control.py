"""Controle de navegadores via Playwright."""

import asyncio
from threading import Thread

_browsers = {}  # instancias ativas


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed() or loop.is_running():
            raise RuntimeError
    except RuntimeError:
        result: dict[str, object] = {}

        def _runner():
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:
                result["error"] = exc

        thread = Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in result:
            raise result["error"]  # type: ignore[misc]
        return result.get("value")

    return loop.run_until_complete(coro)


async def _get_browser(browser_name: str = "chromium"):
    from playwright.async_api import async_playwright

    if browser_name not in _browsers:
        pw = await async_playwright().start()
        # headless=True garante funcionamento sem display em servidor
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        _browsers[browser_name] = {"pw": pw, "browser": browser, "context": context, "page": page}
    return _browsers[browser_name]["page"]


async def _browser_action(parameters: dict) -> str:
    action = parameters.get("action", "")
    browser_name = parameters.get("browser", "chromium")

    try:
        if action == "go_to":
            page = await _get_browser(browser_name)
            url = parameters.get("url", "")
            if not url:
                return "Parametro obrigatorio ausente: url"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"Navegou para {url}"

        elif action == "search":
            page = await _get_browser(browser_name)
            query = parameters.get("query", "")
            engine = parameters.get("engine", "google")
            urls = {
                "google": f"https://www.google.com/search?q={query}",
                "bing": f"https://www.bing.com/search?q={query}",
                "duckduckgo": f"https://duckduckgo.com/?q={query}",
            }
            await page.goto(urls.get(engine, urls["google"]))
            return f"Pesquisado: {query}"

        elif action == "click":
            page = await _get_browser(browser_name)
            selector = parameters.get("selector", "")
            text = parameters.get("text", "")
            if selector:
                await page.click(selector, timeout=10000)
                return f"Clicado no seletor: {selector}"
            elif text:
                await page.get_by_text(text).first.click(timeout=10000)
                return f"Clicado no texto: {text}"
            return "Informe 'selector' ou 'text' para clicar"

        elif action == "type":
            page = await _get_browser(browser_name)
            selector = parameters.get("selector", "")
            text = parameters.get("text", "")
            clear_first = parameters.get("clear_first", True)
            if not selector:
                return "Parametro obrigatorio ausente: selector"
            if clear_first:
                await page.fill(selector, "")
            await page.type(selector, text)
            return f"Digitado: {text}"

        elif action == "scroll":
            page = await _get_browser(browser_name)
            direction = parameters.get("direction", "down")
            amount = parameters.get("amount", 500)
            delta = amount if direction == "down" else -amount
            await page.evaluate(f"window.scrollBy(0, {delta})")
            return f"Scroll {direction} {amount}px"

        elif action == "screenshot":
            page = await _get_browser(browser_name)
            path = parameters.get("path", "browser_screenshot.png")
            await page.screenshot(path=path)
            return f"Screenshot salvo: {path}"

        elif action == "get_text":
            page = await _get_browser(browser_name)
            text = await page.inner_text("body")
            return text[:2000]

        elif action == "get_url":
            page = await _get_browser(browser_name)
            return page.url

        elif action == "back":
            page = await _get_browser(browser_name)
            await page.go_back()
            return "Voltou"

        elif action == "forward":
            page = await _get_browser(browser_name)
            await page.go_forward()
            return "Avancou"

        elif action == "reload":
            page = await _get_browser(browser_name)
            await page.reload()
            return "Recarregado"

        elif action == "new_tab":
            b = _browsers.get(browser_name)
            if not b:
                await _get_browser(browser_name)
                b = _browsers.get(browser_name)
            page = await b["browser"].new_page()
            url = parameters.get("url", "")
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _browsers[f"{browser_name}_tab"] = {**b, "page": page}
            return "Nova aba aberta"

        elif action == "close":
            if browser_name in _browsers:
                await _browsers[browser_name]["browser"].close()
                await _browsers[browser_name]["pw"].stop()
                del _browsers[browser_name]
            return "Browser fechado"

        else:
            return f"Acao desconhecida: {action}"

    except Exception as e:
        return f"Erro browser/{action}: {e}"


def browser_control(parameters: dict, player=None) -> str:
    return _run_async(_browser_action(parameters))
