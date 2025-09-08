from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from PIL import Image

from training.scripts import cli as cli_utils


class DownloadConfig:
    def __init__(self) -> None:
        self.min_dim: int = 0
        self.manifest: bool = False


_config = DownloadConfig()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEMON_DATA_DIR = PROJECT_ROOT / "pokemon_data"


def iter_pokemon_dirs(base_directory: Path) -> Iterable[Path]:
    for child in sorted(base_directory.iterdir()):
        if child.is_directory() and (child / "metadata.json").exists():
            yield child


def iter_all_species_dirs(base_directory: Path) -> Iterable[Path]:
    for child in sorted(base_directory.iterdir()):
        if child.is_directory():
            yield child


def read_display_name(metadata_path: Path) -> str | None:
    try:
        with open(metadata_path, encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        return None
    return None


def find_single_pokemon_directory_by_display_name(
    pokemon_directory: Path, query_name: str
) -> tuple[Path, str] | None:
    normalized_query = query_name.strip().casefold()
    for directory_path in iter_pokemon_dirs(pokemon_directory):
        display_name = read_display_name(directory_path / "metadata.json")
        if not display_name:
            continue
        if display_name.strip().casefold() == normalized_query:
            return directory_path, display_name
    for directory_path in iter_pokemon_dirs(pokemon_directory):
        if directory_path.name.strip().casefold() == normalized_query:
            display_name = (
                read_display_name(directory_path / "metadata.json") or directory_path.name
            )
            return directory_path, display_name
    return None


def sha1_digest(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def hash_existing_images(images_directory: Path) -> set[str]:
    hashes: set[str] = set()
    if not images_directory.exists():
        return hashes
    for f in images_directory.iterdir():
        if not f.is_file():
            continue
        try:
            with open(f, "rb") as fh:
                content = fh.read()
            if content:
                hashes.add(sha1_digest(content))
        except Exception:
            continue
    return hashes


def choose_extension_from_content_type(content_type: str) -> str:
    ctype = (content_type or "").lower()
    if "jpeg" in ctype:
        return ".jpg"
    if "png" in ctype:
        return ".png"
    if "webp" in ctype:
        return ".webp"
    if "gif" in ctype:
        return ".gif"
    return ".img"


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "wb") as f:
        f.write(content)
    tmp.replace(path)


DUCKDUCKGO_BASE = "https://duckduckgo.com/"
DUCKDUCKGO_IMAGE_API = "https://duckduckgo.com/i.js"


async def ddg_get_vqd(session: aiohttp.ClientSession, query: str, *, safe: bool) -> str | None:
    params = {
        "q": query,
        "iax": "images",
        "ia": "images",
        "kp": "1" if safe else "-1",
    }
    async with session.get(
        DUCKDUCKGO_BASE, params=params, timeout=aiohttp.ClientTimeout(total=20)
    ) as resp:
        if resp.status != 200:
            return None
        text = await resp.text()
    for pat in (
        r'vqd\s*=\s*"([^"]+)"',
        r"vqd\s*=\s*'([^']+)'",
        r"\bvqd:'([^']+)'",
        r'\bvqd:"([^"]+)"',
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


async def ddg_fetch_image_urls(
    session: aiohttp.ClientSession,
    query: str,
    *,
    safe: bool,
    max_results: int,
) -> list[str]:
    vqd = await ddg_get_vqd(session, query, safe=safe)
    if not vqd:
        return []
    urls: list[str] = []
    s = 0
    seen: set[str] = set()
    while len(urls) < max_results:
        params = {
            "q": query,
            "vqd": vqd,
            "o": "json",
            "l": "us-en",
            "f": ",,",
            "p": "1" if safe else "-1",
            "s": str(s),
        }
        async with session.get(
            DUCKDUCKGO_IMAGE_API, params=params, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status != 200:
                break
            data = await resp.json(content_type=None)
        results = data.get("results") or []
        if not results:
            break
        for item in results:
            image_url = item.get("image") or item.get("thumbnail") or item.get("url")
            if not image_url:
                continue
            if image_url in seen:
                continue
            seen.add(image_url)
            urls.append(image_url)
            if len(urls) >= max_results:
                break
        s += len(results)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    return urls


BRAVE_IMAGES_BASE = "https://search.brave.com/images"


async def brave_fetch_image_urls(
    session: aiohttp.ClientSession,
    query: str,
    *,
    safe: bool,
    max_results: int,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    offset = 0
    while len(urls) < max_results and offset < 200:
        params = {
            "q": query,
            "source": "web",
            "img": "m",
            "safe": "active" if safe else "off",
            "offset": str(offset),
        }
        async with session.get(
            BRAVE_IMAGES_BASE, params=params, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status != 200:
                break
            html = await resp.text()
        candidates = set()
        for m in re.finditer(
            r'(?:data-src|src|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif))(?:\?[^"\']*)?["\']',
            html,
            flags=re.I,
        ):
            candidates.add(m.group(1))
        for m in re.finditer(
            r'"(https?:\\/\\/[^"\\]+\.(?:jpg|jpeg|png|webp|gif))"', html, flags=re.I
        ):
            url = m.group(1).encode("utf-8").decode("unicode_escape")
            candidates.add(url)
        if not candidates:
            break
        for u in candidates:
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)
            if len(urls) >= max_results:
                break
        offset += 20
        await asyncio.sleep(random.uniform(0.2, 0.4))
    return urls


SEARCH_QUERIES = [
    "Pokemon {name} art",
    "Pokemon {name} card",
    "Pokemon {name} wallpaper",
]


@dataclass
class EngineSpec:
    name: str
    fetcher: callable


def build_engines(selected: str) -> list[EngineSpec]:
    engines: list[EngineSpec] = []
    if selected in ("ddg", "all"):
        engines.append(EngineSpec("ddg", ddg_fetch_image_urls))
    if selected in ("brave", "all"):
        engines.append(EngineSpec("brave", brave_fetch_image_urls))
    return engines


async def fetch_candidate_urls(
    session: aiohttp.ClientSession,
    display_name: str,
    *,
    engines: list[EngineSpec],
    per_species_goal: int,
    safe_search: bool,
) -> list[str]:
    targets: list[tuple[EngineSpec, str]] = []
    queries = [q.format(name=display_name) for q in SEARCH_QUERIES]
    for eng in engines:
        for q in queries:
            targets.append((eng, q))
    random.shuffle(targets)
    unique_urls: list[str] = []
    seen: set[str] = set()
    per_call_quota = max(20, min(100, per_species_goal // max(1, len(targets))))

    async def one(eng: EngineSpec, query: str) -> list[str]:
        try:
            return await eng.fetcher(session, query, safe=safe_search, max_results=per_call_quota)
        except Exception:
            return []

    batch_size = 3
    for i in range(0, len(targets), batch_size):
        batch = targets[i : i + batch_size]
        results = await asyncio.gather(*(one(eng, q) for eng, q in batch))
        for urls in results:
            for u in urls:
                if u in seen:
                    continue
                seen.add(u)
                unique_urls.append(u)
                if len(unique_urls) >= per_species_goal * 3:
                    return unique_urls
        await asyncio.sleep(random.uniform(0.2, 0.4))
    return unique_urls


async def download_many(
    session: aiohttp.ClientSession,
    urls: list[str],
    *,
    concurrency: int,
    min_bytes: int,
    dry_run: bool,
) -> list[tuple[str, bytes | None, str | None]]:
    sem = asyncio.Semaphore(concurrency)

    async def fetch(url: str) -> tuple[str, bytes | None, str | None]:
        async with sem:
            attempts = 0
            while attempts < 3:
                attempts += 1
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(0.05 * attempts)
                            continue
                        ctype = resp.headers.get("Content-Type", "")
                        data = await resp.read()
                        if len(data) < min_bytes:
                            return (url, None, None)
                        return (url, data, ctype)
                except Exception:
                    await asyncio.sleep(0.1 * attempts)
            return (url, None, None)

    return await asyncio.gather(*(fetch(u) for u in urls))


async def process_species(
    directory_path: Path,
    display_name: str,
    *,
    per_species_goal: int,
    engines: list[EngineSpec],
    safe_search: bool,
    concurrency: int,
    overwrite: bool,
    dry_run: bool,
) -> None:
    images_directory = directory_path / "images"
    if overwrite and not dry_run and images_directory.exists():
        for f in images_directory.iterdir():
            try:
                if f.is_file():
                    f.unlink()
            except Exception:
                pass
    existing_hashes = hash_existing_images(images_directory)
    existing_files = list(images_directory.iterdir()) if images_directory.exists() else []
    existing_count = len([f for f in existing_files if f.is_file()])
    remaining = max(0, per_species_goal - existing_count)
    if remaining <= 0 and not overwrite:
        return
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        candidate_urls = await fetch_candidate_urls(
            session,
            display_name,
            engines=engines,
            per_species_goal=per_species_goal * 2,
            safe_search=safe_search,
        )
        if not candidate_urls:
            return
        random.shuffle(candidate_urls)
        results = await download_many(
            session,
            candidate_urls,
            concurrency=concurrency,
            min_bytes=4096,
            dry_run=dry_run,
        )
    saved = 0
    manifest_entries: list[dict] = []
    for url, data, ctype in results:
        if remaining <= 0 and not overwrite:
            break
        if data is None:
            continue
        digest = sha1_digest(data)
        if digest in existing_hashes:
            continue
        too_small = False
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                if _config.min_dim and (w < _config.min_dim or h < _config.min_dim):
                    too_small = True
        except Exception:
            continue
        if too_small:
            continue
        ext = choose_extension_from_content_type(ctype or "")
        filename = f"{digest}{ext}"
        out_path = images_directory / filename
        if dry_run:
            existing_hashes.add(digest)
            remaining = max(0, remaining - 1)
            saved += 1
            if _config.manifest:
                manifest_entries.append({"url": url, "file": out_path.name, "sha1": digest})
            continue
        try:
            atomic_write(out_path, data)
            existing_hashes.add(digest)
            remaining = max(0, remaining - 1)
            saved += 1
            if _config.manifest:
                manifest_entries.append({"url": url, "file": out_path.name, "sha1": digest})
        except Exception:
            pass
    if dry_run:
        pass
    else:
        if _config.manifest and manifest_entries:
            out_manifest = images_directory / "manifest.jsonl"
            try:
                with open(out_manifest, "a", encoding="utf-8") as mf:
                    for e in manifest_entries:
                        mf.write(json.dumps(e) + "\n")
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download diverse images for Pokémon species (DuckDuckGo/Brave)"
    )
    cli_utils.add_dry_run(parser, help="Do not write files; only report actions")
    cli_utils.add_overwrite(parser, help="Re-fetch images (delete existing files first)")
    cli_utils.add_pokemon(
        parser, help="Only process a single Pokémon display name (e.g., 'Bulbasaur')"
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=300,
        help="Target number of images to have per Pokémon folder (default: 300)",
    )
    parser.add_argument(
        "--engines",
        choices=["ddg", "brave", "all"],
        default="all",
        help="Which image engines to use (default: all)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Max concurrent downloads (default: 8)",
    )
    parser.add_argument(
        "--no-safe-search",
        action="store_true",
        help="Disable safe search (enabled by default)",
    )
    parser.add_argument(
        "--min-dim",
        type=int,
        default=128,
        help="Minimum width/height in pixels to accept an image (default: 128)",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Append per-species download entries to images/manifest.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _config.min_dim = max(0, int(getattr(args, "min_dim", 0)))
    _config.manifest = bool(getattr(args, "manifest", False))
    base = POKEMON_DATA_DIR
    if not base.exists():
        return 2
    engines = build_engines(args.engines)
    if not engines:
        return 2
    safe_search = not args.no_safe_search
    if args.pokemon:
        match = find_single_pokemon_directory_by_display_name(base, args.pokemon)
        if not match:
            return 3
        directory_path, display_name = match
        asyncio.run(
            process_species(
                directory_path,
                display_name,
                per_species_goal=max(1, args.number_images),
                engines=engines,
                safe_search=safe_search,
                concurrency=max(1, args.concurrency),
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
        )
        return 0
    for directory_path in iter_all_species_dirs(base):
        display_name = read_display_name(directory_path / "metadata.json") or directory_path.name
        with contextlib.suppress(Exception):
            asyncio.run(
                process_species(
                    directory_path,
                    display_name,
                    per_species_goal=max(1, args.number_images),
                    engines=engines,
                    safe_search=safe_search,
                    concurrency=max(1, args.concurrency),
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                )
            )
        time.sleep(random.uniform(0.05, 0.15))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
