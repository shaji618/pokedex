import argparse
import json
import re
from pathlib import Path

import cli
import requests
from bs4 import BeautifulSoup


try:
    from script_logger import get_script_logger
    from validation_utils import (
        add_validation_args,
        get_sample_pokemon,
        has_complete_sentence,
        should_proceed_after_validation_failure,
    )
except ImportError:
    from scripts.script_logger import get_script_logger
    from scripts.validation_utils import (
        add_validation_args,
        get_sample_pokemon,
        has_complete_sentence,
        should_proceed_after_validation_failure,
    )
SOURCES = [
    "https://pokemondb.net/evolution",
]


def load_metadata(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def fetch_html(url: str, session: requests.Session) -> str | None:
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return None
        return r.text
    except requests.RequestException:
        return None


def parse_evolution_page(html: str) -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    families: list[list[str]] = []
    edges: set[tuple[str, str]] = set()
    for chain in soup.select(".infocard-list-evo"):
        ordered: list[str] = []
        seen: set[str] = set()
        for card in chain.select(".infocard a.ent-name"):
            name = card.get_text(strip=True)
            if not name:
                continue
            key = canonical_key(name)
            base = collapse_form_to_base(key)
            if base and base not in seen:
                ordered.append(base)
                seen.add(base)
        for i in range(len(ordered) - 1):
            edges.add((ordered[i], ordered[i + 1]))
        if ordered:
            families.append(ordered)
    merged: list[list[str]] = []
    for fam in families:
        placed = False
        for m in merged:
            if any(s in m for s in fam):
                for s in fam:
                    if s not in m:
                        m.append(s)
                placed = True
                break
        if not placed:
            merged.append(list(fam))
    out: dict[str, list[str]] = {}
    for fam in merged:
        for member in fam:
            out[member] = fam
    return out, edges


def canonical_key(name: str) -> str:
    s = name.lower()
    s = s.replace("♀", "-f").replace("♂", "-m")
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


_FORM_TOKENS = (
    "alola",
    "alolan",
    "galar",
    "galarian",
    "hisui",
    "hisuan",
    "paldea",
    "paldean",
    "mega",
    "gigantamax",
    "totem",
    "origin",
    "sky",
    "east",
    "west",
    "midday",
    "midnight",
)


def collapse_form_to_base(key: str) -> str:
    parts = [p for p in key.split("-") if p]
    if not parts:
        return key
    filtered = [parts[0]] + [p for p in parts[1:] if p not in _FORM_TOKENS]
    base = "-".join(filtered)
    return base or key


def process_all(overwrite: bool, dry_run: bool, pokemon_filter: str | None = None) -> None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    chains: dict[str, list[str]] = {}
    all_edges: set[tuple[str, str]] = set()
    for url in SOURCES:
        html = fetch_html(url, session)
        if not html:
            continue
        fam_map, edges = parse_evolution_page(html)
        chains.update(fam_map)
        all_edges |= edges
        cli.polite_sleep()
    root = cli.pokemon_data_root()
    species_dirs = cli.filter_pokemon_directories(pokemon_filter, root)
    if pokemon_filter and not species_dirs:
        return
    if pokemon_filter:
        pass
    for directory_path in species_dirs:
        meta_path = directory_path / "metadata.json"
        meta = load_metadata(meta_path)
        name = meta.get("name") or directory_path.name
        key = canonical_key(name)
        chain = (
            chains.get(key)
            or chains.get(canonical_key(name))
            or chains.get(collapse_form_to_base(canonical_key(name)))
        )
        if not chain:
            continue
        seen: set[str] = set()
        dedup_chain = [s for s in chain if not (s in seen or seen.add(s))]
        fam_set = set(dedup_chain)
        fam_edges = sorted([(a, b) for (a, b) in all_edges if a in fam_set and b in fam_set])
        if len(dedup_chain) >= 4:
            outdeg: dict[str, int] = {}
            for a, _b in fam_edges:
                outdeg[a] = outdeg.get(a, 0) + 1
            has_branch = any(v > 1 for v in outdeg.values())
            is_linear = len(fam_edges) == len(dedup_chain) - 1 and not has_branch
            if is_linear:
                root = dedup_chain[0]
                pivot = dedup_chain[1]
                rebuilt = {(root, pivot)}
                for node in dedup_chain[2:]:
                    rebuilt.add((pivot, node))
                fam_edges = sorted(rebuilt)
        if (
            not overwrite
            and meta.get("evolution_chain") == dedup_chain
            and meta.get("evolution_graph") == [{"from": a, "to": b} for (a, b) in fam_edges]
        ):
            continue
        meta["evolution_chain"] = dedup_chain
        meta["evolution_graph"] = [{"from": a, "to": b} for (a, b) in fam_edges]
        if dry_run:
            continue
        cli.atomic_write(meta_path, json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for evolution chains scraper...")
    logger.info("  🌐 Testing pokemondb.net evolution page availability...")
    logger.info("  📋 Using Pokemon with known evolution chains for testing")
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://pokemondb.net/",
            }
        )
        test_url = SOURCES[0]
        response = session.get(test_url, timeout=15)
        if response.status_code != 200:
            logger.info(f"  ❌ pokemondb.net returned HTTP {response.status_code}")
            return False
        if not has_complete_sentence(response.text):
            logger.info("  ❌ pokemondb.net page has no complete sentences (possible error page)")
            return False
        content = response.text.lower()
        evolution_indicators = ["evolution", "evolve", "pokemon", "pokémon", "chain"]
        has_evolution_content = any(indicator in content for indicator in evolution_indicators)
        if not has_evolution_content:
            logger.info("  ❌ pokemondb.net page doesn't contain evolution-related content")
            return False
        if not any(tag in content for tag in ["<div", "<ul", "<li"]):
            logger.info("  ❌ pokemondb.net page doesn't contain expected HTML structure")
            return False
        if len(response.text) < 5000:
            logger.info(f"  ⚠️  pokemondb.net page is quite small ({len(response.text)} chars)")
        logger.info("  🔍 Testing evolution data parsing with edge case Pokemon...")
        test_pokemon = get_sample_pokemon()
        logger.info(f"    Testing: {', '.join(test_pokemon)}")
        try:
            fam_map, edges = parse_evolution_page(response.text)
            found_evolutions = 0
            for pokemon in test_pokemon:
                key = canonical_key(pokemon.replace("_", " ").title())
                base_key = collapse_form_to_base(key)
                found_chain = (
                    fam_map.get(key) or fam_map.get(canonical_key(pokemon)) or fam_map.get(base_key)
                )
                if found_chain and len(found_chain) > 1:
                    found_evolutions += 1
                    logger.info(
                        f"      ✅ {pokemon}: Found evolution chain with {len(found_chain)} members"
                    )
                else:
                    logger.info(
                        f"      ⚠️  {pokemon}: No evolution chain found (may be naming difference)"
                    )
            success_rate = found_evolutions / len(test_pokemon)
            if success_rate >= 0.5:
                logger.info(
                    f"    ✅ Evolution parsing works ({found_evolutions}/{len(test_pokemon)} found)"
                )
            else:
                logger.info(
                    f"    ⚠️  Evolution parsing may have issues ({found_evolutions}/{len(test_pokemon)} found)"
                )
                logger.info("       (This could be due to naming differences between sites)")
        except Exception as e:
            logger.info(f"    ⚠️  Evolution parsing test failed: {e}")
            logger.info("       (Main validation still passed - page is accessible)")
        logger.info("  ✅ pokemondb.net evolution page is accessible with valid data")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except Exception as e:
        logger.info(f"  ❌ Failed to access pokemondb.net: {e}")
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scrape evolution chains into metadata.json from pokemondb.net (updates missing/incorrect evolution data by default)"
    )
    cli.add_overwrite(p, help="Force writing even if evolution data is unchanged")
    cli.add_dry_run(p)
    cli.add_pokemon(
        p, help="Process evolution chains for only a specific Pokemon by name/directory"
    )
    add_validation_args(p)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.validation_only:
        success = validate_before_scraping(args)
        if success:
            return
        else:
            exit(1)
    if not validate_before_scraping(args):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    process_all(overwrite=args.overwrite, dry_run=args.dry_run, pokemon_filter=args.pokemon)


if __name__ == "__main__":
    main()
