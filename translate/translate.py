#!/usr/bin/env python

import importlib
import ast
import csv
import glob
import json
import os
import re
import shutil
from config import *
import deepl

def prompt_select(title, options):
    if not options:
        return ""
    print(title)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    while True:
        choice = input("Select a number: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("Invalid selection.")


def find_lang_dirs(gamepath):
    candidates = [os.path.join(gamepath, "game", "tl"), os.path.join(gamepath, "tl")]
    for root in candidates:
        if os.path.isdir(root):
            lang_dirs = [
                d
                for d in os.listdir(root)
                if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")
            ]
            lang_dirs.sort()
            return root, lang_dirs
    return "", []


def _validate_lang_dir_input(user_input: str, lang_dirs: list[str]) -> str:
    """Return a valid language folder name from lang_dirs.

    Accepts an exact match, or a case-insensitive match mapped to the real folder name.
    Returns "" if not valid.
    """

    if not user_input:
        return ""
    if user_input in lang_dirs:
        return user_input
    mapping = {d.lower(): d for d in lang_dirs}
    return mapping.get(user_input.lower(), "")


def infer_deepl_target_from_lang_dir(lang_dir_value: str):
    if not lang_dir_value:
        return ""
    key = lang_dir_value.strip().lower()
    mapping = {
        "english": "EN-US",
        "en": "EN-US",
        "portuguese": "PT-PT",
        "português": "PT-PT",
        "portugues": "PT-PT",
        "pt": "PT-PT",
        "german": "DE",
        "deutsch": "DE",
        "de": "DE",
        "czech": "CS",
        "cs": "CS",
        "russian": "RU",
        "russia": "RU",
        "ru": "RU",
        "dutch": "NL",
        "netherlands": "NL",
        "nl": "NL",
        "french": "FR",
        "france": "FR",
        "fr": "FR",
        "greek": "EL",
        "el": "EL",
        "spanish": "ES",
        "spain": "ES",
        "es": "ES",
        "italian": "IT",
        "italy": "IT",
        "it": "IT",
        "polish": "PL",
        "poland": "PL",
        "pl": "PL",
        "japanese": "JA",
        "japan": "JA",
        "ja": "JA",
        "korean": "KO",
        "korea": "KO",
        "ko": "KO",
        "chinese": "ZH",
        "china": "ZH",
        "zh": "ZH",
        "turkish": "TR",
        "tr": "TR",
    }
    return mapping.get(key, "")


def resolve_dialogue_file(current_gamepath: str) -> str:
    """Resolve the dialogue CSV path.

    If config.dialogue_path is set, use it.
    Otherwise prefer <gamepath>/<filename> if it exists, else fall back to <cwd>/<filename>.
    """

    if dialogue_path:
        return os.path.abspath(dialogue_path)
    candidate = os.path.join(current_gamepath, filename)
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    return os.path.abspath(filename)


def update_config_selections(
    *,
    selected_game_name: str,
    selected_lang_dir: str,
    selected_lang: str,
    selected_deepl_target_lang: str,
    resolved_dialogue_file: str,
) -> None:
    """Update translate/config.py with the latest interactive selections."""

    try:
        config_module = importlib.import_module("config")
        config_path = os.path.abspath(getattr(config_module, "__file__", ""))
    except Exception:
        print("Warning: could not locate config.py to persist selections.")
        return

    if not config_path or not os.path.exists(config_path):
        print("Warning: config.py not found; selections will not be saved.")
        return

    updates = {
        "game_name": json.dumps(selected_game_name, ensure_ascii=False),
        "lang_dir": json.dumps(selected_lang_dir, ensure_ascii=False),
        "lang": json.dumps(selected_lang, ensure_ascii=False),
        "deepl_target_lang": json.dumps(selected_deepl_target_lang, ensure_ascii=False),
        # Set dialogue_path to the resolved file so future runs use the correct game's dialogue.csv.
        "dialogue_path": json.dumps(resolved_dialogue_file.replace("\\", "/"), ensure_ascii=False),
    }

    patterns = {
        key: re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$") for key in updates.keys()
    }

    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found = {k: False for k in updates.keys()}
    for idx, line in enumerate(lines):
        for key, pattern in patterns.items():
            match = pattern.match(line)
            if match:
                prefix = match.group(1)
                lines[idx] = prefix + updates[key] + "\n"
                found[key] = True
                break

    # If any keys are missing, append them at the end (rare, but keeps things robust).
    missing = [k for k, ok in found.items() if not ok]
    if missing:
        lines.append("\n# Updated automatically by translate.py\n")
        for key in missing:
            lines.append(f"{key} = {updates[key]}\n")

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Saved selections to config: {config_path}")


game = game_dict[game_name]

gamepath = os.path.normpath(game["path"])

tl = deepl.Translator(api_key)


def get_deepl_target_lang():
    return deepl_target_lang or lang


def mask_placeholders(text: str):
    tokens = []

    # Use an uncommon token format that MT engines are less likely to alter.
    def token_for(index: int) -> str:
        return f"⟦PH{index}⟧"

    def repl(match):
        tokens.append(match.group(0))
        return token_for(len(tokens) - 1)

    masked = re.sub(r"\[[^\]]+\]", repl, text)
    masked = re.sub(r"\{[^}]+\}", repl, masked)
    return masked, tokens


def unmask_placeholders(text: str, tokens):
    for i, token in enumerate(tokens):
        text = text.replace(f"⟦PH{i}⟧", token)
    return text


_RENPLY_TRANSLATOR_COMMENT_RE = re.compile(r"\{#[^}]+\}")


def translate_text_safe(text: str):
    if text in no_tl:
        return text

    # Ren'Py translator comment tags (e.g. {#month}) are metadata. DeepL may
    # drop/alter them, so strip them before translating and reattach after.
    comments = _RENPLY_TRANSLATOR_COMMENT_RE.findall(text)
    if comments:
        text = _RENPLY_TRANSLATOR_COMMENT_RE.sub("", text)

    masked, tokens = mask_placeholders(text)
    translated = tl.translate_text(
        text=masked,
        source_lang=game["main_lang"],
        target_lang=get_deepl_target_lang(),
        glossary=glossaries[game["main_lang"]].setdefault(lang, None) if disable_gloss != 0 else None,
    ).text

    placeholders = [f"⟦PH{i}⟧" for i in range(len(tokens))]
    if any(ph not in translated for ph in placeholders):
        print("Warning: placeholder mismatch, using original text:", text)
        if comments:
            return "".join(comments) + text
        return text

    result = unmask_placeholders(translated, tokens)
    if comments:
        result = "".join(comments) + result
    return result


def translate_strings_file(strings_path: str):
    if not os.path.exists(strings_path):
        print(f"Strings file not found, skipping: {strings_path}")
        return

    with open(strings_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    in_strings_block = False
    updated = False

    for i, line in enumerate(lines):
        # Enter/exit translate blocks. We only act inside: translate <lang> strings:
        any_translate = re.match(r"^\s*translate\s+([^\s]+)\s+([^\s]+)\s*:\s*(?:#.*)?$", line)
        if any_translate:
            is_strings = any_translate.group(2).lower() == "strings"
            if is_strings:
                in_strings_block = any_translate.group(1).lower() == lang_dir.lower()
            else:
                in_strings_block = False
            continue

        if not in_strings_block:
            continue

        old_match = re.match(
            r"^(\s*)old\s+((\"([^\"\\]|\\.)*\")|('([^'\\]|\\.)*'))\s*(?:#.*)?$",
            line,
        )
        if not old_match:
            continue

        old_literal = old_match.group(2)
        old_indent = old_match.group(1)

        # Find the next meaningful statement after this old line.
        # This avoids inserting duplicate `new` lines when there is already a `new`
        # (but formatted differently) and prevents orphan `new` lines.
        new_index = None
        j = i + 1
        while j < len(lines):
            peek = lines[j]
            stripped = peek.strip()
            if stripped == "" or peek.lstrip().startswith("#"):
                j += 1
                continue
            if re.match(r"^\s*new\s+", peek):
                new_index = j
            break

        existing_new_text = ""
        existing_new_indent = old_indent
        if new_index is not None:
            existing_new_indent = re.match(r"^\s*", lines[new_index]).group(0)
            # Try to parse an existing literal new "..." or '...'. If it's not a literal,
            # keep existing_new_text empty.
            literal_match = re.match(
                r"^\s*new\s+((\"([^\"\\]|\\.)*\")|('([^'\\]|\\.)*'))\s*(?:#.*)?$",
                lines[new_index],
            )
            if literal_match:
                lit = literal_match.group(1)
                try:
                    existing_new_text = ast.literal_eval(lit)
                except Exception:
                    existing_new_text = lit.strip("\"'")

        try:
            old_text = ast.literal_eval(old_literal)
        except Exception:
            old_text = old_literal.strip("\"")

        if strings_skip_existing and existing_new_text and existing_new_text != old_text:
            continue
        # If there's an existing `new` statement we can't parse, be conservative and keep it.
        if strings_skip_existing and new_index is not None and not existing_new_text:
            continue

        translated = translate_text_safe(old_text)

        new_line = f"{existing_new_indent if new_index is not None else old_indent}new {json.dumps(translated, ensure_ascii=False)}\n"
        if new_index is not None:
            lines[new_index] = new_line
        else:
            lines.insert(i + 1, new_line)
        updated = True

    if updated:
        backup_path = strings_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copyfile(strings_path, backup_path)
        with open(strings_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Updated strings file: {strings_path}")
    else:
        print(f"No strings updates needed: {strings_path}")


def translate_strings_in_dir(tl_dir: str):
    if not os.path.isdir(tl_dir):
        print(f"Strings directory not found, skipping: {tl_dir}")
        return

    patterns = []
    if strings_filename:
        patterns.append(os.path.join(tl_dir, strings_filename))
    if strings_glob:
        patterns.append(os.path.join(tl_dir, strings_glob))

    seen = set()
    found_any = False
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            if os.path.isdir(path):
                continue
            if not path.lower().endswith(".rpy"):
                continue
            if path in seen:
                continue
            seen.add(path)
            found_any = True
            translate_strings_file(path)

    if not found_any:
        print(f"No .rpy translation files found in: {tl_dir}")

print("Game: " + game_name)
print("Game path: " + gamepath)
print("Source language: " + game["main_lang"])
print("Target language: " + lang)
print()
dialogue_file = resolve_dialogue_file(gamepath)
print("Dialogue file: " + dialogue_file)
print("\n")
if input("Are all the details correct? (y/n) ") != "y":
    # Select game
    game_name = prompt_select("Select game:", list(game_dict.keys()))
    game = game_dict[game_name]
    gamepath = os.path.normpath(game["path"])
    dialogue_path = ""  # Reset so resolve_dialogue_file uses game/cwd fallback

    manual_gamepath = input(f"Game path (leave blank to keep {gamepath}): ").strip()
    if manual_gamepath:
        gamepath = os.path.normpath(manual_gamepath)

    # Select language folder
    tl_root, lang_dirs = find_lang_dirs(gamepath)
    if tl_root and lang_dirs:
        print("Translation folder: " + os.path.normpath(tl_root))
        lang_dir = prompt_select("Select language folder:", lang_dirs)
        if lang_dir:
            print("Selected language folder: " + lang_dir)
            print("Translation target folder: " + os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir)))
    elif tl_root:
        print("No language folders found in: " + tl_root)
    else:
        print("Translation folder not found under game path.")

    if tl_root:
        print("Language folders root: " + os.path.normpath(tl_root))
    if tl_root and lang_dirs:
        while True:
            manual_lang = input("Language folder (leave blank to keep selection): ").strip()
            if not manual_lang:
                break
            validated = _validate_lang_dir_input(manual_lang, lang_dirs)
            if validated:
                lang_dir = validated
                print("Selected language folder: " + lang_dir)
                print(
                    "Translation target folder: "
                    + os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir))
                )
                break
            print("Invalid language folder. Please choose one of: " + ", ".join(lang_dirs))
    else:
        manual_lang = input("Language folder (leave blank to keep selection): ").strip()
        if manual_lang:
            print("Warning: cannot validate language folder (tl root not found). Keeping your input.")
            lang_dir = manual_lang
            print("Selected language folder: " + lang_dir)
            print("Translation target folder: " + os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir)))

    # Set target language
    inferred_target = infer_deepl_target_from_lang_dir(lang_dir)
    if inferred_target:
        print("Suggested target language: " + inferred_target)
    else:
        if lang_dir:
            print("No DeepL mapping for folder: " + lang_dir)
    target_input = input("Target language (DeepL code, e.g. EN-GB, EN-US, DE) [Enter to accept suggestion]: ").strip()
    if target_input:
        deepl_target_lang = target_input
        lang = target_input.lower()
    elif inferred_target:
        deepl_target_lang = inferred_target
        lang = inferred_target.lower()

    print("\nUpdated settings:")
    print("Game: " + game_name)
    print("Game path: " + gamepath)
    print("Source language: " + game["main_lang"])
    print("Target language: " + lang)
    print("Language folder: " + lang_dir)
    suggested_dialogue = resolve_dialogue_file(gamepath)
    manual_dialogue = input(f"Dialogue file (leave blank to use {suggested_dialogue}): ").strip()
    if manual_dialogue:
        dialogue_path = manual_dialogue
    dialogue_file = resolve_dialogue_file(gamepath)
    print("Dialogue file: " + dialogue_file)
    print("Translation target folder: " + os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir)))
    print("\n")

# Offer strings-only mode after language folder is finalized.
skip_dialogue = False
raw_skip = input("Skip dialogue translation and only translate strings? (y/n) [n] ").strip().lower()
if raw_skip in {"y", "yes"}:
    skip_dialogue = True
    if not translate_strings:
        translate_strings = 1
    print("Strings-only mode enabled: dialogues will be skipped.")
else:
    print("Dialogue translation enabled.")

# Persist selections for next run
save_raw = input("Save selected game/language to config.py for next run? (y/n) [y] ").strip().lower()
if save_raw in {"", "y", "yes"}:
    update_config_selections(
        selected_game_name=game_name,
        selected_lang_dir=lang_dir,
        selected_lang=lang,
        selected_deepl_target_lang=get_deepl_target_lang(),
        resolved_dialogue_file=dialogue_file,
    )

if not api_key:
    print("DEEPL_API_KEY is not set. Please set the environment variable and retry.")
    exit(1)

if not skip_dialogue:
    if not os.path.exists(dialogue_file):
        print("Dialogue file not found: " + dialogue_file)
        exit(1)

if not skip_dialogue:
    file = open(dialogue_file, encoding='utf-8')
    reader = csv.DictReader(file, delimiter=delimiter) # Interprets the CSV file as a dictionary

    tl_filename = ""
    first = 1
    row_count = 0
    skipped_count = 0
    translated_count = 0
    print("Translating dialogue rows...")
    for row in reader:
        row_count += 1
        # DeepL doesn't accept empty requests, translating [RelVal] is redundant
        if row["Dialogue"] in no_tl:
            skipped_count += 1
            if row_count % 500 == 0:
                print(f"Processed {row_count} rows... (translated {translated_count}, skipped {skipped_count})")
            continue

        if tl_filename != row["Filename"]:
            tl_filename = row["Filename"]
            # Facilitates not-closing unopened files on first pass
            ################################
            if first != 1:
                tl_file.write("\n# AUTO TRANSLATION END\n")
                for i in range(0, 81):
                    tl_file.write("#")
                tl_file.write("\n")
                print("Closing " + gamepath + tl_filename)
                tl_file.close()
            else:
                first = 0

            # Build the target path from scratch, regardless of what the CSV contains.
            # Strip any leading "game/" and any "tl/<lang>/" to get the bare script-relative path.
            norm_tl_filename = tl_filename.replace("\\", "/")
            norm_tl_filename = re.sub(r"^game/", "", norm_tl_filename)
            norm_tl_filename = re.sub(r"^tl/[^/]+/", "", norm_tl_filename)
            target_path = os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir, norm_tl_filename))
            print("Opening " + target_path)
            tl_file = open(target_path, "a", encoding='utf-8')
            tl_file.write("\n")
            for i in range(0, 81):
                tl_file.write("#")
            tl_file.write("\n# AUTO TRANSLATION BEGIN\n\n")
            ################################

        text = translate_text_safe(row["Dialogue"])
        translated_count += 1

        # Python ignores the quotation marks in "[what]"
        if row["Ren'Py Script"] == "[what]":
            row["Ren'Py Script"] = "\"[what]\""
        tl_text = row["Ren'Py Script"].replace("[what]", text)

        print(gamepath + tl_filename + ", " + row["Ren'Py Script"].replace("[what]", row["Dialogue"])+ " -> " + tl_text)
        # input("Okay?")

        # translate german [id]:
        #     c "[what]" with vpunch
        tl_file.write("translate " + lang_dir + " " + row["Identifier"] + ":\n")
        tl_file.write("    " + tl_text)
        tl_file.write("\n\n")

        if row_count % 100 == 0:
            print(f"Processed {row_count} rows... (translated {translated_count}, skipped {skipped_count})")

    if "tl_file" in locals():
        tl_file.write("\n# AUTO TRANSLATION END\n")
        for i in range(0, 81):
            tl_file.write("#")
        tl_file.write("\n")
        tl_file.close()

    print(f"Done. Processed {row_count} rows (translated {translated_count}, skipped {skipped_count}).")
    if row_count == 0:
        print("No data rows found. Check that the delimiter matches the file and that the file contains data.")
else:
    print("Skipping dialogue rows.")

if translate_strings:
    tl_dir = os.path.join(gamepath, "game", "tl", lang_dir)
    translate_strings_in_dir(tl_dir)
