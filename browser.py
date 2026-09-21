"""Safe connection to an already-authenticated Chrome CDP session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from logging import Logger

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from config import AppConfig
from errors import BrowserConnectionError


@dataclass(slots=True)
class ConnectedBrowser:
    browser: Browser
    context: BrowserContext
    page: Page


class BrowserSession:
    """Attach through CDP without owning or closing the user's Chrome process."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.disconnected = asyncio.Event()

    async def connect(self) -> ConnectedBrowser:
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.config.cdp_url,
                timeout=self.config.browser_connect_timeout_ms,
            )
        except PlaywrightError as exc:
            await self.disconnect()
            raise BrowserConnectionError(
                "Could not connect to Chrome on the configured remote-debugging port. "
                "Start Chrome with --remote-debugging-port=9222 and log in manually."
            ) from exc

        self._browser.on("disconnected", lambda _: self.disconnected.set())
        if not self._browser.contexts:
            await self.disconnect()
            raise BrowserConnectionError("Chrome exposed no browser context over CDP.")

        context = self._choose_context(self._browser.contexts)
        context.set_default_timeout(self.config.action_timeout_ms)
        page = self._choose_page(context)
        self.logger.info("Connected to the existing Chrome session at %s", page.url)
        return ConnectedBrowser(self._browser, context, page)

    @staticmethod
    def _choose_context(contexts: list[BrowserContext]) -> BrowserContext:
        with_pages = [context for context in contexts if context.pages]
        return with_pages[0] if with_pages else contexts[0]

    @staticmethod
    def _choose_page(context: BrowserContext) -> Page:
        visible_pages = [page for page in context.pages if page.url != "about:blank"]
        if visible_pages:
            return visible_pages[-1]
        if context.pages:
            return context.pages[-1]
        raise BrowserConnectionError(
            "The connected Chrome context has no page. Open the SIDA site and retry."
        )

    async def disconnect(self) -> None:
        """Disconnect Playwright; never close the user's Chrome browser."""
        self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> ConnectedBrowser:
        return await self.connect()

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        await self.disconnect()

