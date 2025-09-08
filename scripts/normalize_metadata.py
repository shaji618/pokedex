from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cli


QUOTE_NORMALIZATION = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u02bc": "'",
    "\u2032": "'",
    "`": "'",
    "´": "'",
}
BRAND_NORMALIZATION = {
    "POKéMON": "Pokémon",
    "POKEMON": "Pokémon",
    "Pokemon": "Pokémon",
    "pokemon": "Pokémon",
}


def normalize_quotes_and_apostrophes(text: str) -> str:
    for old_char, new_char in QUOTE_NORMALIZATION.items():
        text = text.replace(old_char, new_char)
    return text


def normalize_pokemon_branding(text: str) -> str:
    for old_brand, new_brand in BRAND_NORMALIZATION.items():
        text = text.replace(old_brand, new_brand)
    return text


def normalize_evolution_chain(chain: list[str]) -> tuple[list[str], list[str]]:
    if not isinstance(chain, list):
        return chain, []
    normalized = []
    changes = []
    try:
        import cli
    except ImportError:
        return chain, []
    for entry in chain:
        if not isinstance(entry, str):
            normalized.append(entry)
            continue
        try:
            pokemon_dir = cli.find_pokemon_directory(entry)
            if pokemon_dir and pokemon_dir.name != entry:
                normalized.append(pokemon_dir.name)
                changes.append(f"{entry} -> {pokemon_dir.name}")
            else:
                normalized.append(entry)
        except Exception:
            normalized.append(entry)
    return normalized, changes


def normalize_evolution_graph(graph: list[dict]) -> tuple[list[dict], list[str]]:
    if not isinstance(graph, list):
        return graph, []
    normalized = []
    changes = []
    try:
        import cli
    except ImportError:
        return graph, []
    for edge in graph:
        if not isinstance(edge, dict):
            normalized.append(edge)
            continue
        normalized_edge = edge.copy()
        if "from" in edge and isinstance(edge["from"], str):
            try:
                pokemon_dir = cli.find_pokemon_directory(edge["from"])
                if pokemon_dir and pokemon_dir.name != edge["from"]:
                    normalized_edge["from"] = pokemon_dir.name
                    changes.append(f"from: {edge['from']} -> {pokemon_dir.name}")
            except Exception:
                pass
        if "to" in edge and isinstance(edge["to"], str):
            try:
                pokemon_dir = cli.find_pokemon_directory(edge["to"])
                if pokemon_dir and pokemon_dir.name != edge["to"]:
                    normalized_edge["to"] = pokemon_dir.name
                    changes.append(f"to: {edge['to']} -> {pokemon_dir.name}")
            except Exception:
                pass
        normalized.append(normalized_edge)
    return normalized, changes


def normalize_pokemon_name_in_text(text: str, pokemon_name: str) -> str:
    if not pokemon_name:
        return text
    import re

    caps_name = pokemon_name.upper()
    pattern = r"\b" + re.escape(caps_name) + r"\b"
    text = re.sub(pattern, pokemon_name, text)
    return text


def normalize_all_caps_words(text: str) -> str:
    import re

    caps_words = re.findall(r"\b[A-Z]{3,}\b", text)
    for caps_word in set(caps_words):
        if caps_word in ["USA", "DNA", "GPS", "TV", "PC", "NPC", "HP", "MP", "EXP", "PP"]:
            continue
        if re.match(r"^[IVX]+$", caps_word):
            continue
        title_case = caps_word.title()
        pattern = r"\b" + re.escape(caps_word) + r"\b"
        text = re.sub(pattern, title_case, text)
    return text


def normalize_whitespace(text: str) -> str:
    text = re.sub(r" +", " ", text)
    text = text.strip()
    return text


def normalize_sentence_spacing(text: str) -> str:
    text = re.sub(r"\.([A-Z])", r". \1", text)
    text = re.sub(r"\.  +", ". ", text)
    return text


def normalize_single_text_with_tracking(text: str, pokemon_name: str = "") -> tuple[str, list[str]]:
    if not isinstance(text, str):
        return text, []
    original_text = text
    changes = []
    new_text = normalize_quotes_and_apostrophes(text)
    if new_text != text:
        changes.append("quotes/apostrophes")
        text = new_text
    new_text = normalize_pokemon_branding(text)
    if new_text != text:
        import re

        for old_brand, new_brand in BRAND_NORMALIZATION.items():
            if old_brand in original_text:
                changes.append(f"{old_brand} -> {new_brand}")
        text = new_text
    new_text = normalize_pokemon_name_in_text(text, pokemon_name)
    if new_text != text and pokemon_name:
        changes.append(f"{pokemon_name.upper()} -> {pokemon_name}")
        text = new_text
    new_text = normalize_all_caps_words(text)
    if new_text != text:
        import re

        caps_words = re.findall(r"\b[A-Z]{3,}\b", original_text)
        for caps_word in set(caps_words):
            if caps_word not in ["USA", "DNA", "GPS", "TV", "PC", "NPC", "HP", "MP", "EXP", "PP"]:
                if not re.match(r"^[IVX]+$", caps_word):
                    title_case = caps_word.title()
                    if caps_word in original_text:
                        changes.append(f"{caps_word} -> {title_case}")
        text = new_text
    new_text = normalize_sentence_spacing(text)
    if new_text != text:
        changes.append("sentence spacing")
        text = new_text
    new_text = normalize_whitespace(text)
    if new_text != text:
        changes.append("whitespace")
        text = new_text
    return text, changes


def normalize_single_text(text: str, pokemon_name: str = "") -> str:
    result, _ = normalize_single_text_with_tracking(text, pokemon_name)
    return result


def normalize_text_array(entries: list[str], pokemon_name: str = "") -> list[str]:
    if not isinstance(entries, list):
        return entries
    normalized = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, str):
            continue
        clean_entry = normalize_single_text(entry, pokemon_name)
        if not clean_entry:
            continue
        clean_lower = clean_entry.lower()
        if clean_lower in seen:
            continue
        normalized.append(clean_entry)
        seen.add(clean_lower)
    return normalized


def analyze_changes(old_data: dict, new_data: dict, pokemon_name: str = "") -> dict[str, dict]:
    changes = {}
    old_description = old_data.get("description", "")
    new_description = new_data.get("description", "")
    if old_description != new_description:
        _, description_changes = normalize_single_text_with_tracking(old_description, pokemon_name)
        changes["description"] = {
            "old": old_description,
            "new": new_description,
            "specific_changes": description_changes,
        }
    old_entries = old_data.get("pokedex_entries", [])
    new_entries = new_data.get("pokedex_entries", [])
    if old_entries != new_entries:
        all_entry_changes = []
        removed_duplicates = len(old_entries) != len(new_entries)
        if isinstance(old_entries, list):
            for _i, entry in enumerate(old_entries):
                if isinstance(entry, str):
                    _, entry_changes = normalize_single_text_with_tracking(entry, pokemon_name)
                    if entry_changes:
                        all_entry_changes.extend(entry_changes)
        changes["pokedex_entries"] = {
            "old_count": len(old_entries) if isinstance(old_entries, list) else 0,
            "new_count": len(new_entries) if isinstance(new_entries, list) else 0,
            "removed_duplicates": removed_duplicates,
            "specific_changes": list(set(all_entry_changes)),
        }
    old_chain = old_data.get("evolution_chain", [])
    new_chain = new_data.get("evolution_chain", [])
    if old_chain != new_chain:
        _, chain_changes = normalize_evolution_chain(old_chain)
        if chain_changes:
            changes["evolution_chain"] = {
                "old": old_chain,
                "new": new_chain,
                "specific_changes": chain_changes,
            }
    old_graph = old_data.get("evolution_graph", [])
    new_graph = new_data.get("evolution_graph", [])
    if old_graph != new_graph:
        _, graph_changes = normalize_evolution_graph(old_graph)
        if graph_changes:
            changes["evolution_graph"] = {
                "old": old_graph,
                "new": new_graph,
                "specific_changes": graph_changes,
            }
    return changes


def process_pokemon_metadata(
    pokemon_directory: Path, *, dry_run: bool = False, overwrite: bool = False
) -> tuple[bool, dict]:
    metadata_path = pokemon_directory / "metadata.json"
    if not metadata_path.exists():
        return False, {"error": "metadata.json not found"}
    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return False, {"error": f"Failed to read metadata: {e}"}
    if not isinstance(metadata, dict):
        return False, {"error": "Invalid metadata format"}
    normalized_metadata = metadata.copy()
    pokemon_name = metadata.get("name", "")
    if "description" in metadata and not getattr(process_pokemon_metadata, "_entries_only", False):
        normalized_metadata["description"] = normalize_single_text(
            metadata["description"], pokemon_name
        )
    if "pokedex_entries" in metadata and not getattr(
        process_pokemon_metadata, "_entries_only", False
    ):
        normalized_metadata["pokedex_entries"] = normalize_text_array(
            metadata["pokedex_entries"], pokemon_name
        )
    if "evolution_chain" in metadata:
        normalized_chain, _ = normalize_evolution_chain(metadata["evolution_chain"])
        normalized_metadata["evolution_chain"] = normalized_chain
    if "evolution_graph" in metadata:
        normalized_graph, _ = normalize_evolution_graph(metadata["evolution_graph"])
        normalized_metadata["evolution_graph"] = normalized_graph
    changes = analyze_changes(metadata, normalized_metadata, pokemon_name)
    if not changes and not overwrite:
        return True, {"status": "unchanged", "changes": {}}
    if dry_run:
        return True, {"status": "would_update", "changes": changes}
    try:
        cli.atomic_write(
            metadata_path,
            json.dumps(normalized_metadata, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        return True, {"status": "updated", "changes": changes}
    except Exception as e:
        return False, {"error": f"Failed to write metadata: {e}"}


def log_changes(pokemon_name: str, result: dict) -> None:
    status = result.get("status", "unknown")
    changes = result.get("changes", {})
    if status == "unchanged":
        pass
    elif status == "would_update":
        log_change_details(changes, dry_run=True)
    elif status == "updated":
        log_change_details(changes, dry_run=False)
    elif "error" in result:
        pass


def log_change_details(changes: dict, dry_run: bool = False) -> None:
    if "description" in changes:
        description_changes = changes["description"].get("specific_changes", [])
        if description_changes:
            for _change in description_changes:
                pass
    if "pokedex_entries" in changes:
        entry_info = changes["pokedex_entries"]
        entry_info["old_count"]
        entry_info["new_count"]
        specific_changes = entry_info.get("specific_changes", [])
        if entry_info.get("removed_duplicates"):
            pass
        else:
            pass
        if specific_changes:
            for _change in specific_changes[:10]:
                pass
            if len(specific_changes) > 10:
                pass
    if "evolution_chain" in changes:
        chain_changes = changes["evolution_chain"].get("specific_changes", [])
        if chain_changes:
            for _change in chain_changes:
                pass
    if "evolution_graph" in changes:
        graph_changes = changes["evolution_graph"].get("specific_changes", [])
        if graph_changes:
            for _change in graph_changes:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize text inconsistencies in Pokemon metadata files"
    )
    cli.add_dry_run(parser, help="Show what would be normalized without making changes")
    cli.add_overwrite(parser, help="Force normalization even if no changes detected")
    cli.add_pokemon(parser, help="Process only a specific Pokemon by name/directory")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        metavar="SIZE",
        help="Number of Pokemon to process per batch (default: 50)",
    )
    parser.add_argument(
        "--progress", action="store_true", help="Show progress indicators during processing"
    )
    parser.add_argument(
        "--description-only", action="store_true", help="Only normalize the 'description' field"
    )
    parser.add_argument(
        "--entries-only", action="store_true", help="Only normalize the 'pokedex_entries' field"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pokemon_data_root = cli.pokemon_data_root()
    if not pokemon_data_root.exists():
        return
    process_pokemon_metadata._description_only = args.description_only
    process_pokemon_metadata._entries_only = args.entries_only
    if args.description_only and args.entries_only:
        return
    pokemon_dirs = cli.filter_pokemon_directories(args.pokemon, pokemon_data_root)
    if args.pokemon and not pokemon_dirs:
        return
    if args.dry_run:
        pass
    stats = {"processed": 0, "updated": 0, "unchanged": 0, "errors": 0}
    total_pokemon = len(pokemon_dirs)
    for i, pokemon_directory in enumerate(pokemon_dirs, 1):
        if args.progress and total_pokemon > 10:
            pass
        success, result = process_pokemon_metadata(
            pokemon_directory, dry_run=args.dry_run, overwrite=args.overwrite
        )
        stats["processed"] += 1
        pokemon_name = pokemon_directory.name
        if success:
            status = result.get("status", "unknown")
            if status in ["updated", "would_update"]:
                stats["updated"] += 1
                if args.progress and total_pokemon > 10:
                    pass
            else:
                stats["unchanged"] += 1
                if args.progress and total_pokemon > 10:
                    pass
        else:
            stats["errors"] += 1
            if args.progress and total_pokemon > 10:
                pass
        if not args.progress or total_pokemon <= 10:
            log_changes(pokemon_name, result)
        if i % args.chunk_size == 0 and i < total_pokemon:
            import time

            time.sleep(0.1)
    if args.dry_run:
        pass
    else:
        pass
    if stats["errors"] > 0:
        pass
    if args.dry_run and stats["updated"] > 0:
        pass


if __name__ == "__main__":
    main()
