#!/usr/bin/env python

import argparse
import csv
from datetime import datetime
import importlib
import os
import platform
import re
import subprocess
from pathlib import Path
import sys

from providers import get_provider


_CONFIG_MODULE_NAME = (os.environ.get("VOICEOVER_CONFIG") or "config").strip() or "config"
config = importlib.import_module(_CONFIG_MODULE_NAME)


_TL_LANG_RE = re.compile(r"(?:^|/)game/tl/([^/]+)/", flags=re.IGNORECASE)


def _prompt_game(default_game_name: str) -> str:
    game_names = list(config.game_dict.keys())
    if default_game_name not in config.game_dict:
        default_game_name = game_names[0]

    print("Available games:")
    for idx, name in enumerate(game_names, start=1):
        marker = " (default)" if name == default_game_name else ""
        print(f"  {idx}) {name}{marker}")

    while True:
        raw = input(f"Select game [Enter={default_game_name}]: ").strip()
        if not raw:
            return default_game_name

        if raw.isdigit():
            selected_index = int(raw)
            if 1 <= selected_index <= len(game_names):
                return game_names[selected_index - 1]
            print("Invalid selection. Try again.")
            continue

        if raw in config.game_dict:
            return raw
        print("Unknown game name. Try again.")


def _list_tl_language_folders(game_dir: Path) -> list[str]:
    tl_dir = game_dir / "tl"
    if not tl_dir.exists() or not tl_dir.is_dir():
        return []
    langs = [p.name for p in tl_dir.iterdir() if p.is_dir()]
    langs.sort(key=lambda s: s.casefold())
    return langs


def _normalize_lang_to_folder_case(lang: str, available_lang_folders: list[str]) -> str:
    if not lang:
        return lang
    mapping = {name.casefold(): name for name in available_lang_folders}
    return mapping.get(lang.casefold(), lang)


def _prompt_lang_from_folders(
    current_lang: str,
    game_main_lang: str,
    available_lang_folders: list[str],
    *,
    allow_main_audio: bool = True,
) -> str:
    """Prompt user to select a language folder based on actual game/tl subfolders.

    Returns a string that should be used as the `--lang` value.
    If `allow_main_audio` is True, user can select the main language audio folder.
    """

    if not available_lang_folders:
        # Fall back to free text if the game has no tl folder.
        raw = input(
            f"Language folder is '{current_lang}' but this game's main language is '{game_main_lang}'. "
            f"Press Enter to keep '{current_lang}', or type a new language folder name: "
        ).strip()
        return raw or current_lang

    normalized_current = _normalize_lang_to_folder_case(current_lang, available_lang_folders)

    print("Available tl language folders:")
    if allow_main_audio:
        marker = " (current)" if normalized_current == game_main_lang else ""
        print(f"  0) (main audio folder: {game_main_lang}){marker}")

    for idx, folder in enumerate(available_lang_folders, start=1):
        marker = " (current)" if folder == normalized_current else ""
        print(f"  {idx}) {folder}{marker}")

    prompt_suffix = f"[Enter={normalized_current}]" if normalized_current else ""
    while True:
        raw = input(f"Select language folder {prompt_suffix}: ").strip()
        if not raw:
            return normalized_current

        if allow_main_audio and raw == "0":
            return game_main_lang

        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(available_lang_folders):
                return available_lang_folders[selected - 1]
            print("Invalid selection. Try again.")
            continue

        # Allow typing; normalize casing if it matches a folder.
        return _normalize_lang_to_folder_case(raw, available_lang_folders)


def _log_factory(log_path: str):
    def _log(event: str, identifier: str = "", detail: str = "") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="") as f:
            f.write(f"{timestamp}\t{event}\t{identifier}\t{detail}\n")

    return _log


def _infer_lang_from_filename_column(rows_to_scan: list[dict]) -> str | None:
    langs: list[str] = []
    for row in rows_to_scan[:5000]:
        value = str(row.get("Filename", "") or "")
        if not value:
            continue
        match = _TL_LANG_RE.search(value.replace("\\", "/"))
        if match:
            langs.append(match.group(1))
    if not langs:
        return None
    return max(set(langs), key=langs.count)


def _extract_langs_from_filename_column(rows_to_scan: list[dict]) -> list[str]:
    langs: list[str] = []
    for row in rows_to_scan[:5000]:
        value = str(row.get("Filename", "") or "")
        if not value:
            continue
        match = _TL_LANG_RE.search(value.replace("\\", "/"))
        if match:
            langs.append(match.group(1))
    if not langs:
        return []
    unique_langs = sorted({lang.strip() for lang in langs if lang.strip()}, key=lambda s: s.casefold())
    return unique_langs


def _map_qwen_language(selected_lang: str) -> str | None:
    if not selected_lang:
        return None
    key = selected_lang.strip().lower()
    mapping = {
        "english": "english",
        "en": "english",
        "german": "german",
        "deutsch": "german",
        "de": "german",
        "french": "french",
        "francais": "french",
        "français": "french",
        "fr": "french",
        "spanish": "spanish",
        "espanol": "spanish",
        "español": "spanish",
        "spain": "spanish",
        "es": "spanish",
        "italian": "italian",
        "italiano": "italian",
        "it": "italian",
        "portuguese": "portuguese",
        "portugues": "portuguese",
        "português": "portuguese",
        "pt": "portuguese",
        "russian": "russian",
        "ru": "russian",
        "japanese": "japanese",
        "ja": "japanese",
        "korean": "korean",
        "ko": "korean",
        "chinese": "chinese",
        "zh": "chinese",
    }
    return mapping.get(key)


def _suggest_games_for_character_code(character_code: str, current_game: str) -> list[str]:
    code = character_code.strip()
    if not code:
        return []
    matches: list[str] = []
    for game_name, game in config.game_dict.items():
        if game_name == current_game:
            continue
        voices = game.get("voices", {})
        if isinstance(voices, dict) and code in voices:
            matches.append(game_name)
    return matches


def _play_audio(path: Path) -> None:
    """Play an audio file using the system default player (cross-platform)."""
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.run(["afplay", str(path)], check=True)
        else:
            # Linux: try common players
            for player in ["mpg123", "aplay", "paplay", "ffplay"]:
                if subprocess.run(["which", player], capture_output=True).returncode == 0:
                    subprocess.run([player, str(path)], check=True)
                    return
            print(f"  (No audio player found. File saved at: {path})")
    except Exception as e:
        print(f"  (Could not play audio: {e})")


def _load_dialogue_tab_for_manual(game_dir: Path, selected_lang: str) -> tuple[dict[str, dict], str]:
    """Find and load dialogue.tab for manual ID lookup.

    Looks in the game directory by default, asks user to confirm or provide a path.
    Returns (row_lookup dict, resolved path string).
    """
    # dialogue.tab is exported to the repo root (parent of game/), not inside game/
    default_path = game_dir.parent / "dialogue.tab"

    print("\n--- Dialogue file for ID lookup ---")
    print(f"⚠  Make sure dialogue.tab was extracted in the correct language: '{selected_lang}'")
    print(f"   (In Ren'Py Launcher: 'Extract Dialogue' with that language selected)\n")

    if default_path.exists():
        raw = input(f"Press Enter to use this file, or type a different path:\n  > ").strip()
        if not raw:
            chosen_path = default_path
        else:
            chosen_path = Path(raw)
    else:
        print(f"  Not found at default location: {default_path}")
        raw = input("  Enter path to dialogue.tab: ").strip()
        chosen_path = Path(raw) if raw else default_path

    if not chosen_path.exists():
        print(f"  File not found: {chosen_path}")
        return {}, str(chosen_path)

    delimiter = "\t"
    try:
        with open(chosen_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=delimiter))
        row_lookup = {}
        for row in rows:
            ident = str(row.get("Identifier", "") or "").strip()
            if not ident:
                continue
            # For multi-line blocks, Ren'Py reuses the same ID for all lines.
            # Keep the first occurrence — which is the primary line of the block.
            if ident not in row_lookup:
                row_lookup[ident] = row
        print(f"  Loaded {len(row_lookup)} entries from: {chosen_path}")
        return row_lookup, str(chosen_path)
    except Exception as e:
        print(f"  Error reading dialogue.tab: {e}")
        return {}, str(chosen_path)


def _run_manual_id_mode(
    game: dict,
    selected_game_name: str,
    selected_lang: str,
    selected_provider: str,
    save_dir: Path,
    file_ext: str,
    all_rows: list[dict],
    provider,
    log,
) -> None:
    """Interactive loop: enter IDs manually, generate, preview, keep or retry."""

    voice_dict = game["voices"]
    game_dir = Path(game["savepath"])

    # Load dialogue.tab for ID lookup
    row_lookup, dialogue_tab_path = _load_dialogue_tab_for_manual(game_dir, selected_lang)

    print("\n=== Manual ID Mode ===")
    print("Enter an identifier to (re-)generate a single line.")
    print("Type 'q' or press Enter on an empty line to exit.\n")

    while True:
        raw_id = input("Identifier (or 'q' to quit): ").strip()
        if not raw_id or raw_id.lower() == "q":
            print("Exiting manual mode.")
            break

        # Look up in dialogue.tab
        row = row_lookup.get(raw_id)
        if row is None:
            print(f"  ID '{raw_id}' not found in dialogue.tab.")
            continue

        character_code = str(row.get("Character", "") or "").strip()
        dialogue = str(row.get("Dialogue", "") or "").strip()

        if not dialogue:
            print(f"  ID '{raw_id}' has no dialogue text.")
            continue

        if character_code not in voice_dict or voice_dict[character_code] == 0:
            print(f"  Character code '{character_code}' is not mapped or ignored in voices.")
            continue

        character_name = voice_dict[character_code]
        out_path = save_dir / (raw_id + file_ext)

        print(f"\n  Character : {character_code} → {character_name}")
        print(f"  Dialogue  : {dialogue}")
        print(f"  Output    : {out_path}")

        # Check if file exists
        if out_path.exists():
            overwrite = input("  File already exists. Overwrite? (y/n) [y]: ").strip().lower()
            if overwrite in {"n", "no"}:
                print("  Skipped.")
                continue

        # Generation + retry loop
        while True:
            print("  Generating...")
            extra_context = {
                "identifier": raw_id,
                "character_code": character_code,
                "renpy_script": row.get("Ren'Py Script"),
                "target_language": selected_lang,
            }

            success = provider.generate_audio(
                text=dialogue,
                game_name=selected_game_name,
                character_name=character_name,
                output_path=out_path,
                extra_context=extra_context,
            )

            if not success:
                print("  Generation failed.")
                log("error", raw_id, "manual mode generation failed")
                retry = input("  Try again? (y/n) [n]: ").strip().lower()
                if retry in {"y", "yes"}:
                    continue
                break

            log("generated", raw_id, f"manual mode provider={selected_provider}")
            print("  Generated. Playing...")
            _play_audio(out_path)

            keep = input("  Keep this file? (Enter/y=keep / n=regenerate / s=skip): ").strip().lower()
            if keep in {"y", "yes", ""}:
                print("  Kept.")
                break
            elif keep in {"s", "skip"}:
                # Remove the file if user doesn't want it
                try:
                    out_path.unlink()
                except Exception:
                    pass
                print("  Skipped (file removed).")
                break
            else:
                # Remove and regenerate
                try:
                    out_path.unlink()
                except Exception:
                    pass
                print("  Regenerating...")
                continue


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--game", dest="game_name", help="Game name (must match a key in config.game_dict)")
    parser.add_argument("--lang", dest="lang", help="Ren'Py tl language folder (e.g., English, German)")
    parser.add_argument(
        "--provider",
        dest="provider",
        help="TTS provider: 'elevenlabs' or 'qwen' (default from config.py)",
    )
    parser.add_argument(
        "--no-select",
        action="store_true",
        help="Do not prompt for selection; use config defaults/CLI args",
    )
    parser.add_argument(
        "--dialogue",
        dest="dialogue_path",
        help="Path to dialogue file (defaults to Tools/Missing Files/dialogue_missing.tab if present)",
    )
    parser.add_argument(
        "--log",
        dest="log_path",
        help="Path to log file (default: Tools/voiceover/log.txt)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    default_dialogue_missing = os.path.normpath(
        os.path.join(str(script_dir), "..", "Missing Files", "dialogue_missing.tab")
    )

    dialogue_path = args.dialogue_path
    if not dialogue_path:
        dialogue_path = default_dialogue_missing if os.path.exists(default_dialogue_missing) else config.filename
    csv_path = Path(dialogue_path) if os.path.isabs(dialogue_path) else (script_dir / dialogue_path)
    if not csv_path.exists():
        print(f"Dialogue file not found: {csv_path}")
        return 2

    # Auto-detect delimiter by peeking at first line
    delimiter = config.delimiter
    if csv_path.suffix.lower() in {".tab", ".tsv"}:
        delimiter = "\t"
        # But check if file actually uses commas instead
        try:
            with open(csv_path, "r", encoding="utf-8") as peek:
                first_line = peek.readline()
                if "," in first_line and "\t" not in first_line:
                    delimiter = ","
        except Exception:
            pass

    log_path = args.log_path or str(script_dir / "log.txt")
    log = _log_factory(log_path)
    setattr(config, "voiceover_log_path", log_path)

    selected_game_name = args.game_name or config.game_name
    if (
        not args.no_select
        and not args.game_name
        and sys.stdin is not None
        and sys.stdin.isatty()
    ):
        selected_game_name = _prompt_game(selected_game_name)

    selected_provider = args.provider or getattr(config, "tts_provider", "elevenlabs")
    if (
        not args.no_select
        and not args.provider
        and sys.stdin is not None
        and sys.stdin.isatty()
    ):
        provider_options = ["elevenlabs", "qwen"]
        default_provider = selected_provider if selected_provider in provider_options else "elevenlabs"
        print("Available TTS providers:")
        for idx, name in enumerate(provider_options, start=1):
            marker = " (default)" if name == default_provider else ""
            print(f"  {idx}) {name}{marker}")

        while True:
            raw = input(f"Select provider [Enter={default_provider}]: ").strip()
            if not raw:
                selected_provider = default_provider
                break
            if raw.isdigit():
                selected_index = int(raw)
                if 1 <= selected_index <= len(provider_options):
                    selected_provider = provider_options[selected_index - 1]
                    break
                print("Invalid selection. Try again.")
                continue
            if raw.lower() in provider_options:
                selected_provider = raw.lower()
                break
            print("Unknown provider. Try again.")

    if selected_game_name not in config.game_dict:
        print(f"Unknown game '{selected_game_name}'. Available: {', '.join(config.game_dict.keys())}")
        return 2

    game = config.game_dict[selected_game_name]
    voice_dict = game["voices"]

    # Load rows
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    base_game_dir = Path(game["savepath"])
    available_lang_folders = _list_tl_language_folders(base_game_dir)

    selected_lang = args.lang or config.lang

    # If we are using dialogue_missing.tab and user didn't specify --lang,
    # infer the language folder from the Filename column.
    if not args.lang and delimiter == "\t" and csv_path.name.lower() == "dialogue_missing.tab":
        inferred_lang = _infer_lang_from_filename_column(rows)
        if inferred_lang and inferred_lang != selected_lang:
            print(f"Detected language folder from input: '{inferred_lang}'")
            if sys.stdin is not None and sys.stdin.isatty() and not args.no_select:
                raw = input(
                    f"Use '{inferred_lang}' for output folder? (Enter=yes / type to override / n=keep '{selected_lang}'): "
                ).strip()
                if raw == "" or raw.lower() == "y":
                    selected_lang = inferred_lang
                elif raw.lower() == "n":
                    pass
                else:
                    selected_lang = raw
            else:
                selected_lang = inferred_lang

    # Expand available language folders with languages found in input file
    if delimiter == "\t" and fieldnames and "Filename" in fieldnames:
        inferred_langs = _extract_langs_from_filename_column(rows)
        if inferred_langs:
            existing = {name.casefold(): name for name in available_lang_folders}
            for lang in inferred_langs:
                if lang.casefold() not in existing:
                    available_lang_folders.append(lang)
            available_lang_folders.sort(key=lambda s: s.casefold())

    # Normalize selected language to the actual folder capitalization if possible.
    selected_lang = _normalize_lang_to_folder_case(selected_lang, available_lang_folders)

    # Interactive selection of language folders (based on actual game/tl subfolders).
    if (
        not args.no_select
        and sys.stdin is not None
        and sys.stdin.isatty()
    ):
        selected_lang = _prompt_lang_from_folders(
            selected_lang,
            game["main_lang"],
            available_lang_folders,
            allow_main_audio=True,
        )

    # If user selected a tl language that doesn't exist, warn (still allow output).
    if selected_lang != game["main_lang"] and available_lang_folders:
        if selected_lang not in available_lang_folders:
            print(
                f"Warning: selected language folder '{selected_lang}' was not found under '{base_game_dir / 'tl'}'. "
                f"Available: {', '.join(available_lang_folders)}"
            )

    save_dir = base_game_dir
    if selected_lang != game["main_lang"]:
        save_dir = save_dir / "tl" / selected_lang
    save_dir = save_dir / "audio" / "voice"
    save_dir.mkdir(parents=True, exist_ok=True)

    if selected_provider == "qwen":
        mapped_lang = _map_qwen_language(selected_lang)
        if mapped_lang:
            setattr(config, "qwen_force_language", mapped_lang)

    provider_file_ext_map = {
        "elevenlabs": ".mp3",
        "qwen": ".mp3",  # Default, can be changed via qwen_output_format config
    }
    if selected_provider == "qwen":
        output_format = str(getattr(config, "qwen_output_format", "mp3") or "mp3").strip().lower()
        if output_format in {"wav", "wave"}:
            file_ext = ".wav"
        elif output_format == "ogg":
            file_ext = ".ogg"
        else:
            file_ext = ".mp3"
    else:
        file_ext = provider_file_ext_map.get(selected_provider, ".mp3")

    print("Game: " + selected_game_name)
    print("Language: " + selected_lang)
    print("TTS Provider: " + selected_provider)
    print("Interpreted file: " + str(csv_path))
    print("Output folder: " + str(save_dir))
    print("Log file: " + log_path)
    print("Example path: " + str(save_dir / f"[Identifier]{file_ext}"))
    print("================================")
    print("\n")

    inchar = input("Are all the details correct? (y/n) ")
    if inchar != "y":
        return 1

    # --- Mode selection ---
    print("\nHow do you want to generate?")
    print("  1) Process dialogue file (normal batch mode)")
    print("  2) Enter IDs manually (single-line mode with playback)")
    mode_raw = input("Select mode [Enter=1]: ").strip()
    manual_mode = mode_raw == "2"

    print("Initializing TTS provider... this can take a while for Qwen.")
    try:
        provider = get_provider(selected_provider, config, log)
        provider.initialize()
    except Exception as ex:
        print(f"Error initializing TTS provider '{selected_provider}': {ex}")
        return 2

    # Load all rows for lookup (also used by manual mode)
    # rows already loaded above — reuse them.

    if manual_mode:
        _run_manual_id_mode(
            game=game,
            selected_game_name=selected_game_name,
            selected_lang=selected_lang,
            selected_provider=selected_provider,
            save_dir=save_dir,
            file_ext=file_ext,
            all_rows=rows,  # used only as fallback for character code lookup
            provider=provider,
            log=log,
        )
        provider.cleanup()
        return 0

    log("run_start", detail=f"game={selected_game_name} lang={selected_lang} provider={selected_provider} input={csv_path} out={save_dir}")

    generated = 0
    skipped = 0
    errored = 0

    # Deduplicate: for multi-line translate blocks, Ren'Py reuses the same ID.
    # Keep only the first occurrence (primary line) per identifier.
    seen_ids: set[str] = set()
    deduped_rows = []
    for row in rows:
        ident = str(row.get("Identifier", "") or "").strip()
        if ident and ident not in seen_ids:
            seen_ids.add(ident)
            deduped_rows.append(row)
    if len(deduped_rows) < len(rows):
        print(f"Note: deduplicated {len(rows) - len(deduped_rows)} duplicate ID rows (multi-line translate blocks).")
    rows = deduped_rows

    print(f"\n=== Processing {len(rows)} rows ===")
    for idx, row in enumerate(rows, start=1):
        identifier = str(row.get("Identifier", "") or "").strip()
        if not identifier:
            skipped += 1
            log("skip", detail="missing Identifier")
            continue

        character_code = str(row.get("Character", "") or "").strip()
        if character_code in voice_dict:
            character_name = voice_dict[character_code]
            if character_name == 0:
                skipped += 1
                log("skip", identifier, f"ignored character code='{character_code}'")
                continue
        else:
            skipped += 1
            suggestions = _suggest_games_for_character_code(character_code, selected_game_name)
            hint = f"; appears in: {', '.join(suggestions)}" if suggestions else ""
            log("skip", identifier, f"unknown character code='{character_code}'{hint}")
            continue

        dialogue = str(row.get("Dialogue", "") or "")
        if not dialogue:
            skipped += 1
            log("skip", identifier, "empty Dialogue")
            continue

        out_path = save_dir / (identifier + file_ext)
        
        # Show progress
        if idx % 10 == 0 or idx == 1:
            print(f"Progress: {idx}/{len(rows)} ({generated} generated, {skipped} skipped, {errored} errors)")
        
        # Build extra context for provider
        extra_context = {
            "identifier": identifier,
            "character_code": character_code,
            "renpy_script": row.get("Ren'Py Script"),
            "target_language": selected_lang,
        }
        
        # Generate audio using the provider
        success = provider.generate_audio(
            text=dialogue,
            game_name=selected_game_name,
            character_name=character_name,
            output_path=out_path,
            extra_context=extra_context,
        )
        
        if success:
            generated += 1
        else:
            errored += 1

    # Post-run verification: anything from the input still missing is logged.
    still_missing = []
    for row in rows:
        identifier = str(row.get("Identifier", "") or "").strip()
        if not identifier:
            continue
        out_path = save_dir / (identifier + file_ext)
        if not out_path.exists():
            still_missing.append(identifier)
            log("still_missing", identifier, f"expected at '{save_dir}'")

    print("\nSummary:")
    print(f"Generated: {generated}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errored}")
    print(f"Still missing after run: {len(still_missing)}")
    if still_missing:
        print(f"See log: {log_path}")

    log("run_end", detail=f"generated={generated} skipped={skipped} errors={errored} still_missing={len(still_missing)}")
    
    # Clean up provider resources
    provider.cleanup()
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
