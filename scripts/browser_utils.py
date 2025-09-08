"""Browser utilities for Pokemon data scraping.

⚠️  DEPRECATED: These utilities were used for pokemon.com validation which has been
removed from the main build pipeline. Serebii.net is now the single authoritative source.

This module is kept for compatibility with standalone scripts but is no longer
used in the main build_pokemon_data.py process.
"""

import types
from typing import Any

from playwright.async_api import async_playwright
from script_logger import get_script_logger


class PersistentBrowserSession:
    def __init__(self) -> None:
        self.browser = None
        self.context = None
        self.playwright = None
        self.playwright_cm = None

    async def extract_pokemon_data(self, url: str) -> dict | None:
        if not self.browser or not self.context:
            raise RuntimeError(
                "Browser session not started. Use 'async with' or call start() first."
            )
        logger = get_script_logger()
        try:
            logger.info(f"  🎭 Using persistent browser for {url}")
            page = await self.context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                content = await page.content()
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(content, "html.parser")
                if "Pardon Our Interruption" in content:
                    logger.warning("  ❌ Still blocked even with persistent browser")
                    return None
                try:
                    from scrape_official_pokemon_site import _extract_pokemon_data_from_soup
                except ImportError:
                    from scripts.scrape_official_pokemon_site import _extract_pokemon_data_from_soup
                return _extract_pokemon_data_from_soup(soup, url)
            finally:
                await page.close()
        except Exception as e:
            logger.error(f"  ❌ Persistent browser extraction failed: {e}")
            return None

    async def __aenter__(self) -> "PersistentBrowserSession":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        logger = get_script_logger()
        try:
            logger.info("  🎭 Starting persistent browser session...")
            self.playwright_cm = async_playwright()
            self.playwright = await self.playwright_cm.__aenter__()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=VizDisplayCompositor",
                ],
            )
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            logger.info("  ✅ Browser session ready")
        except ImportError:
            logger.error("  ❌ Playwright not available, install with: pip install playwright")
            raise
        except Exception as e:
            logger.error(f"  ❌ Failed to start browser session: {e}")
            raise

    async def close(self) -> None:
        logger = get_script_logger()
        try:
            if self.browser:
                logger.info("  🎭 Closing browser session...")
                await self.browser.close()
            if hasattr(self, "playwright_cm") and self.playwright_cm:
                await self.playwright_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"  ⚠️ Error closing browser session: {e}")
        self.browser = None
        self.context = None
        self.playwright = None
        self.playwright_cm = None


async def validate_pokemon_with_shared_browser(
    pokemon_list: list[str],
    *,
    update: bool = True,
    dry_run: bool = False,
    browser_session: PersistentBrowserSession | None = None,
) -> dict[str, Any]:
    try:
        from scrape_official_pokemon_site import process_pokemon_batch
    except ImportError:
        from scripts.scrape_official_pokemon_site import process_pokemon_batch
    return await process_pokemon_batch(
        pokemon_list, update=update, dry_run=dry_run, browser_session=browser_session
    )
