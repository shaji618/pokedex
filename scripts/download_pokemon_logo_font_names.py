import argparse
import asyncio
import base64
import contextlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any


try:
    from playwright.async_api import BrowserContext, Page
except ImportError:
    from typing import Any as BrowserContext
    from typing import Any as Page
import cli


try:
    from script_logger import get_script_logger
    from validation_utils import add_validation_args, should_proceed_after_validation_failure
except ImportError:
    from scripts.script_logger import get_script_logger
    from scripts.validation_utils import (
        add_validation_args,
        should_proceed_after_validation_failure,
    )
POKEMON_FONT_GENERATOR_URL = "https://textcraft.net/style/Textcraft/pokemon"


def iter_pokemon_dirs(pokemon_data_directory: Path) -> Iterable[Path]:
    for child in sorted(pokemon_data_directory.iterdir()):
        if child.is_dir() and (child / "metadata.json").exists():
            yield child


def read_display_name(metadata_path: Path) -> str | None:
    try:
        import json

        with open(metadata_path, encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None
    except Exception:
        return None


async def fill_text_input(page: Any, text: str) -> None:
    try:
        await page.wait_for_selector("#yourtext", timeout=5000)
        await page.wait_for_selector("#yourtext2", timeout=5000)
        await page.wait_for_selector("#yourtext3", timeout=5000)
        await page.fill("#yourtext2", "")
        await page.fill("#yourtext3", "")
        await page.fill("#yourtext", "")
        await page.type("#yourtext", text)
        return
    except Exception:
        pass
    try:
        form = page.locator("form").first
        await form.wait_for(timeout=2000)
        try:
            for sid in ["#yourtext2", "#yourtext3"]:
                el = page.locator(sid)
                if await el.count() > 0:
                    await el.fill("")
        except Exception:
            pass
        first_input = form.locator("input[type='text']").first
        await first_input.wait_for(timeout=2000)
        await first_input.fill("")
        await first_input.type(text)
        return
    except Exception as exc:
        raise RuntimeError("Could not locate the Textcraft text inputs on the page") from exc


async def click_generate(page: Any) -> None:
    try:
        await page.locator("#createbutton").click()
        return
    except Exception:
        pass
    for selector in [
        "button#createbutton",
        "#createbutton",
        "button:has-text('Create')",
        "input[type='submit']",
    ]:
        try:
            await page.locator(selector).first.click()
            return
        except Exception:
            continue
    raise RuntimeError("Could not locate the Create button on the page")


async def disable_solid_background(page: Any) -> None:
    return


async def extract_generated_png_bytes(page: Page, *, wait_timeout_ms: int = 15000) -> bytes:
    await page.wait_for_selector("#output img", timeout=wait_timeout_ms)
    img = page.locator("#output img").last
    await img.wait_for(timeout=wait_timeout_ms)
    src = await img.get_attribute("src")
    if not isinstance(src, str) or not src:
        raise RuntimeError("#output img has no src attribute")
    if src.startswith("data:image/"):
        header, b64 = src.split(",", 1)
        png_bytes = base64.b64decode(b64)
        return png_bytes
    if src.startswith("http://") or src.startswith("https://"):
        import requests as _requests

        resp = _requests.get(src, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} while downloading image: {src}")
        return resp.content
    raise RuntimeError(f"Unsupported img src format: {src}")


async def generate_logo_png_bytes(
    display_name: str,
    *,
    debug_directory: Path | None = None,
    browser_context: BrowserContext | None = None,
) -> bytes:
    if browser_context:
        page = await browser_context.new_page()
        try:
            return await _generate_logo_with_page(page, display_name, debug_directory)
        finally:
            await page.close()
    else:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                return await _generate_logo_with_page(page, display_name, debug_directory)
            finally:
                await context.close()
                await browser.close()


async def _generate_logo_with_page(
    page: Page, display_name: str, debug_directory: Path | None
) -> bytes:
    await page.goto(POKEMON_FONT_GENERATOR_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    try:
        initial_source = await page.evaluate(
            "() => { const img = document.querySelector('#output img'); return img ? img.getAttribute('src') : null; }"
        )
    except Exception:
        initial_source = None
    await fill_text_input(page, display_name)
    await click_generate(page)
    with contextlib.suppress(Exception):
        await page.wait_for_function(
            "(initial) => {\n"
            "  const img = document.querySelector('#output img');\n"
            "  if (!img || !img.src) return false;\n"
            "  const src = img.src;\n"
            "  if (initial && src === initial) return false;\n"
            "  if (src.startsWith('data:image/')) return true;\n"
            "  if (/\\/data\\//.test(src)) return true;\n"
            "  if (src.includes('/styles/')) return false;\n"
            "  return false;\n"
            "}",
            arg=initial_source,
            timeout=30000,
        )
    try:
        png_bytes = await extract_generated_png_bytes(page)
        return png_bytes
    except Exception:
        if debug_directory is not None:
            debug_directory.mkdir(parents=True, exist_ok=True)
            try:
                before_html = await page.content()
                (debug_directory / "debug_dom.html").write_text(before_html, encoding="utf-8")
            except Exception:
                pass
            try:
                img_bytes = await page.screenshot(full_page=True, type="png")
                (debug_directory / "debug_fullpage.png").write_bytes(img_bytes)
            except Exception:
                pass
        raise


def find_single_pokemon_directory_by_display_name(
    pokemon_data_directory: Path, query_name: str
) -> tuple[Path, str] | None:
    directory_path = cli.find_pokemon_directory(query_name, pokemon_data_directory)
    if not directory_path:
        return None
    display_name = read_display_name(directory_path / "metadata.json")
    if not display_name:
        display_name = directory_path.name
    return directory_path, display_name


def write_png(
    target_directory: Path, filename: str, png_bytes: bytes, overwrite: bool = False
) -> Path:
    target_directory.mkdir(parents=True, exist_ok=True)
    out_path = target_directory / filename
    if out_path.exists() and not overwrite:
        return out_path
    with open(out_path, "wb") as f:
        f.write(png_bytes)
    return out_path


async def process_single(
    pokemon_directory: Path,
    display_name: str,
    overwrite: bool,
    debug: bool,
    browser_context: BrowserContext | None = None,
) -> Path:
    debug_directory = (pokemon_directory / ".logo_debug") if debug else None
    out_path = pokemon_directory / "name.png"
    if out_path.exists() and not overwrite:
        return out_path
    png_bytes = await generate_logo_png_bytes(
        display_name, debug_directory=debug_directory, browser_context=browser_context
    )
    return write_png(pokemon_directory, "name.png", png_bytes, overwrite=overwrite)


async def process_all(
    pokemon_data_directory: Path,
    overwrite: bool,
    debug: bool,
    browser_context: BrowserContext | None = None,
) -> None:
    for directory_path in iter_pokemon_dirs(pokemon_data_directory):
        display_name = read_display_name(directory_path / "metadata.json")
        if not display_name:
            continue
        out_path = directory_path / "name.png"
        if out_path.exists() and not overwrite:
            continue
        try:
            await process_single(
                directory_path,
                display_name,
                overwrite=overwrite,
                debug=debug,
                browser_context=browser_context,
            )
            await asyncio.sleep(0.25)
        except Exception:
            pass


async def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for Pokemon logo font generator...")
    logger.info("  🌐 Testing textcraft.net Pokemon font generator availability...")
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.goto(
                POKEMON_FONT_GENERATOR_URL, wait_until="domcontentloaded", timeout=15000
            )
            title = await page.title()
            if not title:
                logger.info("  ❌ textcraft.net page has no title")
                await browser.close()
                return False
            content = await page.content()
            content_lower = content.lower()
            generator_indicators = ["pokemon", "font", "text", "generator", "style"]
            has_generator_content = any(
                indicator in content_lower for indicator in generator_indicators
            )
            if not has_generator_content:
                logger.info("  ❌ textcraft.net page doesn't contain font generator content")
                await browser.close()
                return False
            if not any(element in content_lower for element in ["<input", "<button", "<form"]):
                logger.info("  ❌ textcraft.net page doesn't contain expected form elements")
                await browser.close()
                return False
            await browser.close()
        logger.info("  ✅ textcraft.net Pokemon font generator is accessible")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except ImportError:
        logger.info("  ❌ Playwright not available - install with: pip install playwright")
        return False
    except Exception as e:
        logger.info(f"  ❌ Failed to access textcraft.net: {e}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Pokémon logo names via font generator")
    cli.add_pokemon(
        parser,
        help="Run for a single Pokémon display name (e.g., 'Bulbasaur'). If omitted, run for all.",
    )
    cli.add_overwrite(parser, help="Overwrite existing 'name.png' files if present.")
    cli.add_debug(
        parser, help="Write debug HTML and screenshots to '<pokemon>/.logo_debug' on failures."
    )
    add_validation_args(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validation_only:
        success = asyncio.run(validate_before_scraping(args))
        if success:
            return 0
        else:
            exit(1)
    if not asyncio.run(validate_before_scraping(args)):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    cli.project_root()
    pokemon_data_directory = cli.pokemon_data_root()
    if not pokemon_data_directory.exists():
        return 1
    if args.pokemon:
        match = find_single_pokemon_directory_by_display_name(pokemon_data_directory, args.pokemon)
        if not match:
            return 2
        directory_path, display_name = match
        try:
            asyncio.run(
                process_single(
                    directory_path, display_name, overwrite=args.overwrite, debug=args.debug
                )
            )
            return 0
        except Exception:
            return 3
    else:
        try:
            asyncio.run(
                process_all(pokemon_data_directory, overwrite=args.overwrite, debug=args.debug)
            )
            return 0
        except Exception:
            return 4


if __name__ == "__main__":
    raise SystemExit(main())
