from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import requests
from script_logger import get_script_logger


try:
    import cli
except ImportError:
    try:
        from scripts import cli
    except ImportError:
        import sys

        sys.path.append(str(Path(__file__).resolve().parent.parent))
        import cli
VALID_POKEMON_NAME_PATTERN = re.compile(r"^[A-Za-z\-'.♀♂\s]+$")
VALID_DESCRIPTION_MIN_LENGTH = 15
VALID_DESCRIPTION_MAX_LENGTH = 800
VALID_PRONUNCIATION_PATTERN = re.compile(r"^[A-Za-z\-\s\(\)\/]+$")
ERROR_INDICATORS = [
    "404",
    "not found",
    "error",
    "forbidden",
    "access denied",
    "page not available",
    "temporarily unavailable",
    "maintenance",
]


def get_user_agent_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def check_website_health(url: str, expected_content: str | list[str] | None = None) -> bool:
    try:
        response = requests.get(url, timeout=15, headers=get_user_agent_headers())
        if response.status_code != 200:
            return False
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("image/"):
            return len(response.content) > 1000
        if expected_content:
            content_checks = (
                expected_content if isinstance(expected_content, list) else [expected_content]
            )
            return any(check.lower() in response.text.lower() for check in content_checks)
        return True
    except Exception:
        return False


def validate_pokemon_name(name: str) -> list[str]:
    issues = []
    if not name:
        issues.append("Name is empty")
        return issues
    if len(name) < 2:
        issues.append("Name too short")
    elif len(name) > 25:
        issues.append("Name suspiciously long")
    if not re.match(r"^[A-Za-z\-'.♀♂\s:]+$", name):
        issues.append("Name contains invalid characters")
    if re.search(r"\d", name) and name not in [
        "Type: Null",
        "Porygon2",
    ]:
        issues.append("Name contains unexpected numbers")
    if name.lower() in ERROR_INDICATORS:
        issues.append("Name appears to be an error message")
    if any(char in name for char in ["<", ">", "&", ";"]):
        issues.append("Name contains HTML/markup artifacts")
    return issues


def validate_pokedex_number(num: int | str) -> list[str]:
    issues = []
    try:
        if isinstance(num, str):
            if not num.isdigit():
                issues.append("Pokedex number is not numeric")
                return issues
            num = int(num)
        if not isinstance(num, int):
            issues.append("Pokedex number must be an integer")
        elif num <= 0:
            issues.append(f"Pokedex number {num} must be positive")
        elif num > 9999:
            issues.append(f"Pokedex number {num} seems unreasonably high (possible data error)")
    except (ValueError, TypeError):
        issues.append("Invalid Pokedex number format")
    return issues


def validate_pokemon_types(types: list[str]) -> list[str]:
    issues = []
    if not types:
        issues.append("No types provided")
        return issues
    if len(types) > 2:
        issues.append(f"Too many types ({len(types)}) - Pokemon have at most 2 types")
    for ptype in types:
        if not isinstance(ptype, str):
            issues.append(f"Type '{ptype}' is not a string")
        elif not cli.is_valid_type(ptype.lower()):
            issues.append(f"Unknown Pokemon type: '{ptype}'")
    return issues


def validate_description_text(text: str) -> list[str]:
    issues = []
    if not text or not text.strip():
        issues.append("Description is empty")
        return issues
    text = text.strip()
    if len(text) < VALID_DESCRIPTION_MIN_LENGTH:
        issues.append(f"Description too short ({len(text)} chars)")
    elif len(text) > VALID_DESCRIPTION_MAX_LENGTH:
        issues.append(f"Description unusually long ({len(text)} chars)")
    text_lower = text.lower()
    for indicator in ERROR_INDICATORS:
        if indicator in text_lower:
            issues.append(f"Description contains error indicator: '{indicator}'")
    if text.count(".") == 0 and text.count("!") == 0 and text.count("?") == 0:
        issues.append("Description has no sentence endings")
    if "<" in text and ">" in text:
        issues.append("Description contains HTML tags")
    words = text.split()
    if len(words) > 10 and len(set(words)) < len(words) * 0.5:
        issues.append("Description appears to have repeated content")
    return issues


def validate_pokedex_entries(entries: list[str]) -> list[str]:
    issues = []
    if not entries:
        issues.append("No Pokedex entries provided")
        return issues
    for i, entry in enumerate(entries):
        if not isinstance(entry, str):
            issues.append(f"Entry {i} is not a string")
            continue
        entry = entry.strip()
        if len(entry) < 10:
            issues.append(f"Entry {i} too short")
        elif len(entry) > 500:
            issues.append(f"Entry {i} unusually long")
        entry_lower = entry.lower()
        for indicator in ERROR_INDICATORS:
            if indicator in entry_lower:
                issues.append(f"Entry {i} contains error indicator: '{indicator}'")
    unique_entries = set(entries)
    if len(unique_entries) < len(entries):
        issues.append(f"Found {len(entries) - len(unique_entries)} duplicate entries")
    return issues


def validate_pronunciation_data(phonetic: str | None, ipa: str | None) -> list[str]:
    issues = []
    if not phonetic and not ipa:
        issues.append("No pronunciation data provided")
        return issues
    if phonetic:
        if len(phonetic) < 2:
            issues.append("Phonetic pronunciation too short")
        elif not re.match(VALID_PRONUNCIATION_PATTERN, phonetic):
            issues.append("Phonetic pronunciation contains unexpected characters")
    if ipa:
        if len(ipa) < 2:
            issues.append("IPA pronunciation too short")
        elif len(ipa) > 50:
            issues.append("IPA pronunciation suspiciously long")
    return issues


def validate_evolution_data(
    evolution_chain: list[str], evolution_graph: dict[str, Any]
) -> list[str]:
    issues = []
    if evolution_chain:
        for pokemon in evolution_chain:
            if not isinstance(pokemon, str):
                issues.append("Evolution chain contains non-string entries")
            elif len(pokemon) < 2:
                issues.append("Evolution chain contains suspiciously short names")
    if evolution_graph:
        if not isinstance(evolution_graph, dict):
            issues.append("Evolution graph is not a dictionary")
        else:
            for key, value in evolution_graph.items():
                if not isinstance(key, str):
                    issues.append("Evolution graph has non-string keys")
                if not isinstance(value, list):
                    issues.append("Evolution graph has non-list values")
    return issues


def validate_generation_number(generation: int | str | None) -> list[str]:
    issues = []
    if generation is None:
        return issues
    try:
        if isinstance(generation, str):
            roman_to_int = {
                "I": 1,
                "II": 2,
                "III": 3,
                "IV": 4,
                "V": 5,
                "VI": 6,
                "VII": 7,
                "VIII": 8,
                "IX": 9,
            }
            if generation.upper() in roman_to_int:
                generation = roman_to_int[generation.upper()]
            else:
                generation = int(generation)
        if not isinstance(generation, int):
            issues.append("Generation must be an integer")
        elif not (1 <= generation <= 9):
            issues.append(f"Generation {generation} outside expected range (1-9)")
    except (ValueError, TypeError):
        issues.append("Invalid generation format")
    return issues


def validate_url_domain(url: str, expected_domain: str) -> list[str]:
    issues = []
    if not url:
        issues.append("URL is empty")
        return issues
    if not url.startswith(("http://", "https://")):
        issues.append("URL missing protocol")
    if expected_domain not in url:
        issues.append(f"URL not from expected domain '{expected_domain}'")
    return issues


def run_sample_test(
    test_func: callable, test_cases: list[str], script_name: str, success_threshold: float = 0.8
) -> bool:
    logger = get_script_logger()
    if not test_cases:
        logger.info(f"  ⚠️  {script_name}: No test cases provided")
        return True
    logger.info(f"  🧪 {script_name}: Testing {len(test_cases)} samples...")
    success_count = 0
    for test_case in test_cases:
        try:
            result = test_func(test_case)
            if result:
                success_count += 1
                logger.info(f"    ✅ {test_case}: OK")
            else:
                logger.info(f"    ❌ {test_case}: Failed")
        except Exception as e:
            logger.info(f"    💥 {test_case}: Error - {e}")
    success_rate = success_count / len(test_cases)
    if success_rate >= success_threshold:
        logger.info(
            f"    ✅ Sample test passed ({success_count}/{len(test_cases)}) - {success_rate:.1%}"
        )
        return True
    else:
        logger.info(
            f"    ❌ Sample test failed ({success_count}/{len(test_cases)}) - {success_rate:.1%} below {success_threshold:.0%} threshold"
        )
        return False


def get_sample_pokemon(count: int = 7, filter_for: str = "general") -> list[str]:
    edge_case_sample = [
        "pikachu",
        "farfetch_d",
        "ho_oh",
        "mr_mime",
        "nidoran_male",
        "nidoran_female",
        "charizard",
    ]
    if filter_for == "evolution_chains":
        evolution_sample = [
            "pikachu",
            "farfetch_d",
            "mr_mime",
            "nidoran_male",
            "nidoran_female",
            "charizard",
        ]
        return evolution_sample[:count]
    return edge_case_sample[:count]


def get_real_pokemon_metadata(directory_name: str) -> dict[str, Any] | None:
    pokemon_data_directory = cli.pokemon_data_root()
    metadata_path = pokemon_data_directory / directory_name / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def compare_scraped_vs_real_data(
    scraped_data: dict[str, Any], real_data: dict[str, Any]
) -> list[str]:
    differences = []
    scraped_number = scraped_data.get("pokedex_number")
    real_number = real_data.get("pokedex_number")
    if scraped_number != real_number:
        differences.append(f"Pokedex number: scraped={scraped_number}, real={real_number}")
    scraped_name = scraped_data.get("name")
    real_name = real_data.get("name")
    if scraped_name != real_name:
        differences.append(f"Name: scraped='{scraped_name}', real='{real_name}'")
    scraped_types = sorted(cli.normalize_types(scraped_data.get("types", [])))
    real_types = sorted(cli.normalize_types(real_data.get("types", [])))
    if scraped_types != real_types:
        differences.append(f"Types: scraped={scraped_types}, real={real_types}")
    return differences


def validate_metadata_file(metadata_path: Path) -> list[str]:
    issues = []
    if not metadata_path.exists():
        issues.append("Metadata file does not exist")
        return issues
    try:
        with open(metadata_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        issues.append(f"Invalid JSON: {e}")
        return issues
    except Exception as e:
        issues.append(f"Cannot read file: {e}")
        return issues
    if "name" in data:
        issues.extend(validate_pokemon_name(data["name"]))
    else:
        issues.append("Missing required field: name")
    if "pokedex_number" in data:
        issues.extend(validate_pokedex_number(data["pokedex_number"]))
    else:
        issues.append("Missing required field: pokedex_number")
    if "types" in data:
        issues.extend(validate_pokemon_types(data["types"]))
    else:
        issues.append("Missing required field: types")
    if "description" in data:
        issues.extend(validate_description_text(data["description"]))
    if "pokedex_entries" in data:
        issues.extend(validate_pokedex_entries(data["pokedex_entries"]))
    if "generation" in data:
        issues.extend(validate_generation_number(data["generation"]))
    if "phonetic" in data or "ipa" in data:
        issues.extend(validate_pronunciation_data(data.get("phonetic"), data.get("ipa")))
    if "evolution_chain" in data or "evolution_graph" in data:
        issues.extend(
            validate_evolution_data(
                data.get("evolution_chain", []), data.get("evolution_graph", {})
            )
        )
    return issues


def add_validation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip pre-flight validation checks"
    )
    parser.add_argument("--force", action="store_true", help="Continue even if validation fails")
    parser.add_argument(
        "--validation-only",
        action="store_true",
        help="Only run validation checks, don't perform scraping",
    )


def should_proceed_after_validation_failure(force: bool) -> bool:
    logger = get_script_logger()
    if force:
        logger.info("⚠️  Continuing anyway due to --force flag")
        return True
    else:
        logger.info("💡 Use --force to override validation failures")
        return False


def has_complete_sentence(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return False
    return bool(re.search(r"[.!?]\s+\S", text) or re.search(r"[.!?]$", text.strip()))


def remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return without_accents


def normalize_pokemon_name(name: str, format_type: str = "directory") -> str:
    """Normalize Pokemon name to various formats (directory, url, simple).

    Args:
        name: Pokemon name to normalize (e.g., "Mr. Mime", "Farfetch'd", "Nidoran♀")
        format_type: Output format - "directory", "url", or "simple"

    Returns:
        Normalized name based on format_type
    """
    if not name:
        return "unknown" if format_type == "directory" else ""

    normalized = name.strip().lower()

    # Handle gender symbols first (before removing special chars)
    if "♀" in normalized:
        normalized = normalized.replace("♀", "")
        gender_suffix = (
            "_female" if format_type == "directory" else "-female" if format_type == "url" else ""
        )
    elif "♂" in normalized:
        normalized = normalized.replace("♂", "")
        gender_suffix = (
            "_male" if format_type == "directory" else "-male" if format_type == "url" else ""
        )
    elif normalized.endswith(("-f", "_f")):
        normalized = normalized[:-2]
        gender_suffix = (
            "_female" if format_type == "directory" else "-female" if format_type == "url" else ""
        )
    elif normalized.endswith(("-m", "_m")):
        normalized = normalized[:-2]
        gender_suffix = (
            "_male" if format_type == "directory" else "-male" if format_type == "url" else ""
        )
    else:
        gender_suffix = ""

    # Handle punctuation based on format type
    if format_type == "simple":
        # Simple: just remove common punctuation
        normalized = re.sub(r"[''.]", "", normalized)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
    elif format_type == "url":
        # URL: use hyphens, remove apostrophes
        normalized = normalized.replace("'", "").replace("'", "")
        normalized = normalized.replace(".", "-")
        normalized = re.sub(r"[^\w\s-]", "", normalized)
        normalized = re.sub(r"[\s-]+", "-", normalized)
        normalized = normalized.strip("-")
    else:  # directory format (default)
        # Directory: use underscores
        normalized = normalized.replace("'", "_")  # Farfetch'd -> farfetch_d
        normalized = normalized.replace(".", "_")  # Mr. Mime -> mr_mime
        normalized = normalized.replace("-", "_")  # Ho-oh -> ho_oh
        normalized = normalized.replace(":", "_")  # Type: Null -> type_null
        normalized = re.sub(r"[^\w\s_]", "", normalized)
        normalized = re.sub(r"[\s_]+", "_", normalized)
        normalized = normalized.strip("_")

    # Add gender suffix
    if gender_suffix and normalized:
        if format_type == "simple":
            normalized = f"{normalized} {gender_suffix.strip('_-')}"
        else:
            normalized = f"{normalized}{gender_suffix}"

    return normalized or ("unknown" if format_type == "directory" else "")


def resolve_pokemon_query(query: str, root: Path | None = None) -> tuple[str | None, str]:
    if root is None:
        root = cli.pokemon_data_root()
    if not root.exists():
        return None, f"Pokemon data directory doesn't exist: {root}"
    query = str(query).strip()
    available_pokemon = {}
    directory_names = set()
    for directory_path in root.iterdir():
        if not directory_path.is_dir() or directory_path.name.startswith("."):
            continue
        directory_names.add(directory_path.name)
        metadata_path = directory_path / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                available_pokemon[directory_path.name] = metadata
            except (json.JSONDecodeError, OSError):
                available_pokemon[directory_path.name] = {}
    if not available_pokemon:
        return None, "No Pokemon data found in directory"
    if query.isdigit():
        pokedex_num = int(query)
        for dir_name, metadata in available_pokemon.items():
            if metadata.get("pokedex_number") == pokedex_num:
                return (
                    dir_name,
                    f"Found by Pokedex number #{pokedex_num}: {metadata.get('name', dir_name)}",
                )
        return None, f"No Pokemon found with Pokedex number #{pokedex_num}"
    query_lower = query.lower()
    for dir_name in directory_names:
        if dir_name.lower() == query_lower:
            metadata = available_pokemon.get(dir_name, {})
            display_name = metadata.get("name", dir_name)
            return dir_name, f"Found by directory name: {display_name}"
    for dir_name, metadata in available_pokemon.items():
        display_name = metadata.get("name", "")
        if display_name and display_name.lower() == query_lower:
            return dir_name, f"Found by display name: {display_name}"
    normalized_query = normalize_pokemon_name(query)
    for dir_name in directory_names:
        if dir_name == normalized_query:
            metadata = available_pokemon.get(dir_name, {})
            display_name = metadata.get("name", dir_name)
            return (
                dir_name,
                f"Found by normalized name '{query}' → '{normalized_query}': {display_name}",
            )
    query_no_accents = remove_accents(query_lower)
    for dir_name, metadata in available_pokemon.items():
        display_name = metadata.get("name", "")
        if display_name:
            display_no_accents = remove_accents(display_name.lower())
            if display_no_accents == query_no_accents:
                return dir_name, f"Found by accent-insensitive match '{query}' → '{display_name}'"
    partial_matches = []
    for dir_name, metadata in available_pokemon.items():
        display_name = metadata.get("name", "")
        if display_name and query_lower in display_name.lower():
            partial_matches.append((dir_name, display_name))
    if len(partial_matches) == 1:
        dir_name, display_name = partial_matches[0]
        return dir_name, f"Found by partial name match: {display_name}"
    elif len(partial_matches) > 1:
        match_list = [
            f"#{available_pokemon[dn].get('pokedex_number', '?'):03d} {display}"
            for dn, display in partial_matches[:5]
        ]
        return None, f"Multiple matches found for '{query}': {', '.join(match_list)}"
    dir_matches = [dn for dn in directory_names if query_lower in dn.lower()]
    if len(dir_matches) == 1:
        dir_name = dir_matches[0]
        metadata = available_pokemon.get(dir_name, {})
        display_name = metadata.get("name", dir_name)
        return dir_name, f"Found by partial directory match: {display_name}"
    elif len(dir_matches) > 1:
        return None, f"Multiple directory matches found for '{query}': {', '.join(dir_matches[:5])}"
    suggestions = []
    example_pokemon = list(available_pokemon.items())[:5]
    for dir_name, metadata in example_pokemon:
        display_name = metadata.get("name", dir_name)
        pokedex_num = metadata.get("pokedex_number", "")
        if pokedex_num:
            suggestions.append(f"#{pokedex_num:03d} {display_name}")
        else:
            suggestions.append(display_name)
    suggestion_text = f"Available examples: {', '.join(suggestions)}"
    return None, f"No Pokemon found for '{query}'. {suggestion_text}"


def find_pokemon_directory_robust(
    query: str, root: Path | None = None, *, verbose: bool = True
) -> Path | None:
    if root is None:
        root = cli.pokemon_data_root()
    directory_name, message = resolve_pokemon_query(query, root)
    if verbose:
        logger = get_script_logger()
        if directory_name:
            logger.info(f"✅ {message}")
        else:
            logger.error(f"❌ {message}")
    return root / directory_name if directory_name else None


def get_pokemon_suggestions(
    query: str, root: Path | None = None, max_suggestions: int = 5
) -> list[str]:
    if root is None:
        root = cli.pokemon_data_root()
    if not root.exists():
        return []
    query_lower = query.lower()
    suggestions = []
    for directory_path in root.iterdir():
        if not directory_path.is_dir() or directory_path.name.startswith("."):
            continue
        metadata_path = directory_path / "metadata.json"
        display_name = directory_path.name
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                display_name = metadata.get("name", directory_path.name)
            except (json.JSONDecodeError, OSError):
                pass
        if query_lower in display_name.lower() or query_lower in directory_path.name.lower():
            suggestions.append(display_name)
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def get_audio_properties(audio_path: Path) -> dict[str, Any] | None:
    try:
        import wave

        if not audio_path.exists():
            return None
        file_size = audio_path.stat().st_size
        file_format = audio_path.suffix.lower()
        properties = {
            "file_size": file_size,
            "format": file_format,
            "sample_rate": None,
            "duration": None,
            "channels": None,
        }
        if file_format == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wav_file:
                    properties.update(
                        {
                            "sample_rate": wav_file.getframerate(),
                            "duration": wav_file.getnframes() / wav_file.getframerate(),
                            "channels": wav_file.getnchannels(),
                            "bit_depth": wav_file.getsampwidth() * 8,
                        }
                    )
            except Exception:
                try:
                    import json
                    import subprocess

                    result = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "quiet",
                            "-print_format",
                            "json",
                            "-show_format",
                            "-show_streams",
                            str(audio_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        duration = float(data["format"]["duration"])
                        sample_rate = int(data["streams"][0]["sample_rate"])
                        channels = int(data["streams"][0]["channels"])
                        properties.update(
                            {
                                "sample_rate": sample_rate,
                                "duration": duration,
                                "channels": channels,
                            }
                        )
                except Exception:
                    pass
        else:
            try:
                import librosa

                y, sr = librosa.load(str(audio_path), sr=None)
                properties.update(
                    {
                        "sample_rate": sr,
                        "duration": len(y) / sr,
                        "channels": 1 if len(y.shape) == 1 else y.shape[1],
                    }
                )
                if len(y) > 0:
                    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
                    properties["spectral_centroid_mean"] = float(spectral_centroid.mean())
                    rms = librosa.feature.rms(y=y)[0]
                    properties["rms_mean"] = float(rms.mean())
            except ImportError:
                pass
            except Exception:
                pass
        return properties
    except Exception:
        return None


def compare_audio_files(
    local_path: Path,
    remote_path: Path | None = None,
    remote_url: str | None = None,
    tolerance: dict[str, float] | None = None,
) -> tuple[bool, str]:
    if tolerance is None:
        tolerance = {
            "duration": 0.1,
            "sample_rate": 0.05,
            "file_size": 0.15,
            "spectral_centroid": 0.1,
            "rms": 0.2,
        }
    local_props = get_audio_properties(local_path)
    if not local_props:
        return False, "Cannot read local audio file"
    if remote_path:
        remote_props = get_audio_properties(remote_path)
        if not remote_props:
            return False, "Cannot read remote audio file"
    else:
        return True, "No remote file provided - assuming local file is valid"
    differences = []
    if local_props["duration"] and remote_props["duration"]:
        duration_diff = abs(local_props["duration"] - remote_props["duration"])
        if duration_diff > tolerance["duration"]:
            differences.append(f"duration differs by {duration_diff:.3f}s")
    if local_props["sample_rate"] and remote_props["sample_rate"]:
        sr_diff = (
            abs(local_props["sample_rate"] - remote_props["sample_rate"])
            / local_props["sample_rate"]
        )
        if sr_diff > tolerance["sample_rate"]:
            differences.append(f"sample rate differs by {sr_diff:.1%}")
    size_diff = abs(local_props["file_size"] - remote_props["file_size"]) / max(
        local_props["file_size"], 1
    )
    if size_diff > tolerance["file_size"]:
        differences.append(f"file size differs by {size_diff:.1%}")
    if local_props.get("spectral_centroid_mean") and remote_props.get("spectral_centroid_mean"):
        sc_diff = abs(
            local_props["spectral_centroid_mean"] - remote_props["spectral_centroid_mean"]
        )
        sc_diff_pct = sc_diff / max(local_props["spectral_centroid_mean"], 1)
        if sc_diff_pct > tolerance["spectral_centroid"]:
            differences.append(f"spectral content differs by {sc_diff_pct:.1%}")
    if local_props.get("rms_mean") and remote_props.get("rms_mean"):
        rms_diff = abs(local_props["rms_mean"] - remote_props["rms_mean"])
        rms_diff_pct = rms_diff / max(local_props["rms_mean"], 1)
        if rms_diff_pct > tolerance["rms"]:
            differences.append(f"volume level differs by {rms_diff_pct:.1%}")
    if differences:
        return False, f"Audio files differ: {', '.join(differences)}"
    else:
        return True, "Audio files are similar"


def validate_audio_file(audio_path: Path, expected_duration: float | None = None) -> dict[str, Any]:
    result = {
        "valid": False,
        "checks": {
            "file_exists": False,
            "file_readable": False,
            "format_supported": False,
            "duration_reasonable": False,
            "audio_properties_valid": False,
        },
        "properties": {},
        "errors": [],
    }
    if not audio_path.exists():
        result["errors"].append("Audio file does not exist")
        return result
    result["checks"]["file_exists"] = True
    properties = get_audio_properties(audio_path)
    if not properties:
        result["errors"].append("Cannot read audio file properties")
        return result
    result["checks"]["file_readable"] = True
    result["properties"] = properties
    supported_formats = [".wav", ".mp3", ".ogg", ".flac", ".m4a"]
    if properties["format"] in supported_formats:
        result["checks"]["format_supported"] = True
    else:
        result["errors"].append(f"Unsupported audio format: {properties['format']}")
    duration = properties.get("duration")
    if duration:
        if 0.1 <= duration <= 10.0:
            result["checks"]["duration_reasonable"] = True
        else:
            result["errors"].append(f"Unusual duration: {duration:.2f}s (expected 0.1-10.0s)")
        if expected_duration and abs(duration - expected_duration) > 0.5:
            result["errors"].append(
                f"Duration mismatch: got {duration:.2f}s, expected ~{expected_duration:.2f}s"
            )
    else:
        if result["checks"]["file_exists"] and result["checks"]["format_supported"]:
            result["checks"]["duration_reasonable"] = True
    sample_rate = properties.get("sample_rate")
    if sample_rate:
        if 8000 <= sample_rate <= 96000:
            result["checks"]["audio_properties_valid"] = True
        else:
            result["errors"].append(f"Unusual sample rate: {sample_rate}Hz")
    else:
        if result["checks"]["file_exists"] and result["checks"]["format_supported"]:
            result["checks"]["audio_properties_valid"] = True
    result["valid"] = all(result["checks"].values())
    return result


def calculate_image_hash(image_path: Path) -> str | None:
    try:
        import imagehash
        from PIL import Image

        with Image.open(image_path) as img:
            phash = imagehash.phash(img, hash_size=8)
            return str(phash)
    except ImportError:
        return None
    except Exception:
        return None


def download_image_temporarily(url: str, session: requests.Session | None = None) -> bytes | None:
    if session is None:
        session = requests.Session()
        session.headers.update(get_user_agent_headers())
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            return None
        if len(response.content) < 100:
            return None
        return response.content
    except Exception:
        return None


def compare_images_by_hash(
    local_path: Path, remote_url: str, threshold: int = 5, session: requests.Session | None = None
) -> tuple[bool, str]:
    try:
        import io

        import imagehash
        from PIL import Image

        if not local_path.exists():
            return False, "Local image file does not exist"
        try:
            with Image.open(local_path) as local_img:
                local_hash = imagehash.phash(local_img, hash_size=8)
        except Exception as e:
            return False, f"Cannot read local image: {e}"
        remote_data = download_image_temporarily(remote_url, session)
        if not remote_data:
            return False, "Cannot download remote image"
        try:
            with Image.open(io.BytesIO(remote_data)) as remote_img:
                remote_hash = imagehash.phash(remote_img, hash_size=8)
        except Exception as e:
            return False, f"Cannot process remote image: {e}"
        difference = abs(local_hash - remote_hash)
        is_similar = difference <= threshold
        if is_similar:
            return True, f"Images match (hash difference: {difference})"
        else:
            return (
                False,
                f"Images differ significantly (hash difference: {difference} > {threshold})",
            )
    except ImportError:
        return True, "imagehash library not available - skipping validation"
    except Exception as e:
        return False, f"Image comparison failed: {e}"


def validate_image_integrity(
    local_path: Path, remote_url: str, session: requests.Session | None = None
) -> dict[str, Any]:
    result = {
        "valid": False,
        "checks": {
            "file_exists": False,
            "file_readable": False,
            "size_reasonable": False,
            "dimensions_valid": False,
            "hash_match": False,
        },
        "details": {},
        "errors": [],
    }
    if not local_path.exists():
        result["errors"].append("Local image file does not exist")
        return result
    result["checks"]["file_exists"] = True
    try:
        from PIL import Image

        with Image.open(local_path) as img:
            local_size = local_path.stat().st_size
            local_dims = img.size
            local_format = img.format
        result["checks"]["file_readable"] = True
        result["details"]["local"] = {
            "size_bytes": local_size,
            "dimensions": local_dims,
            "format": local_format,
        }
        if 10 <= local_size <= 50 * 1024 * 1024:
            result["checks"]["size_reasonable"] = True
        else:
            result["errors"].append(f"Unusual file size: {local_size} bytes")
        if all(1 <= dim <= 5000 for dim in local_dims):
            result["checks"]["dimensions_valid"] = True
        else:
            result["errors"].append(f"Unusual dimensions: {local_dims}")
    except Exception as e:
        result["errors"].append(f"Cannot read local image: {e}")
        return result
    remote_data = download_image_temporarily(remote_url, session)
    if not remote_data:
        result["errors"].append("Cannot download remote image for comparison")
        result["valid"] = result["checks"]["file_readable"] and result["checks"]["size_reasonable"]
        return result
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(remote_data)) as remote_img:
            remote_dims = remote_img.size
            remote_format = remote_img.format
        result["details"]["remote"] = {
            "size_bytes": len(remote_data),
            "dimensions": remote_dims,
            "format": remote_format,
        }
        if local_dims == remote_dims:
            result["details"]["dimensions_match"] = True
        else:
            result["errors"].append(
                f"Dimension mismatch: local {local_dims} vs remote {remote_dims}"
            )
    except Exception as e:
        result["errors"].append(f"Cannot process remote image: {e}")
        result["valid"] = result["checks"]["file_readable"] and result["checks"]["size_reasonable"]
        return result
    is_similar, hash_message = compare_images_by_hash(
        local_path, remote_url, threshold=5, session=session
    )
    result["checks"]["hash_match"] = is_similar
    result["details"]["hash_comparison"] = hash_message
    if not is_similar and "imagehash library not available" not in hash_message:
        result["errors"].append(hash_message)
    result["valid"] = (
        result["checks"]["file_exists"]
        and result["checks"]["file_readable"]
        and result["checks"]["size_reasonable"]
        and result["checks"]["dimensions_valid"]
        and (
            result["checks"]["hash_match"]
            or "imagehash library not available" in result["details"].get("hash_comparison", "")
        )
    )
    return result


def validate_pokemon_images(
    pokemon_directory: Path, urls: dict[str, str], session: requests.Session | None = None
) -> dict[str, dict[str, Any]]:
    results = {}
    for image_name, url in urls.items():
        image_path = pokemon_directory / image_name
        validation_result = validate_image_integrity(image_path, url, session)
        results[image_name] = validation_result
    return results
