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
        **( {"formality": formality} if formality else {} ),
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


def collect_translated_strings(tl_dir: str) -> set:
    """Pre-scan all tl .rpy files; return old strings that already have a filled-in new translation."""
    translated = set()
    old_re = re.compile(r"^\s*old\s+((\"([^\"\\]|\\.)*\")|('([^'\\]|\\.)*'))\s*(?:#.*)?$")
    new_re = re.compile(r"^\s*new\s+((\"([^\"\\]|\\.)*\")|('([^'\\]|\\.)*'))\s*(?:#.*)?$")
    for rpy_path in glob.glob(os.path.join(tl_dir, '**', '*.rpy'), recursive=True):
        try:
            with open(rpy_path, encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue
        in_strings_block = False
        pending_old = None
        for line in lines:
            any_translate = re.match(r"^\s*translate\s+([^\s]+)\s+([^\s]+)\s*:\s*(?:#.*)?$", line)
            if any_translate:
                in_strings_block = (
                    any_translate.group(2).lower() == "strings"
                    and any_translate.group(1).lower() == lang_dir.lower()
                )
                pending_old = None
                continue
            if not in_strings_block:
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            om = old_re.match(line)
            if om:
                try:
                    pending_old = ast.literal_eval(om.group(1))
                except Exception:
                    pending_old = om.group(1).strip("\"'")
                continue
            if pending_old is not None:
                nm = new_re.match(line)
                if nm:
                    try:
                        new_val = ast.literal_eval(nm.group(1))
                    except Exception:
                        new_val = nm.group(1).strip("\"'")
                    if new_val and new_val != pending_old:
                        translated.add(pending_old)
                    pending_old = None
    return translated


def translate_strings_file(strings_path: str, globally_translated: set = None):
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

        # Skip if this old string is already translated in another tl file (prevents cross-file duplicates)
        if globally_translated and old_text in globally_translated and not existing_new_text:
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


def strip_empty_strings_blocks(tl_dir: str) -> int:
    """Remove empty translate X strings: blocks from all .rpy files in tl_dir.

    Ren'Py errors on startup when a 'translate X strings:' block exists but
    contains no old/new pairs (only whitespace or comments). This strips them.
    Returns the number of files modified.
    """
    header_re = re.compile(r'^translate\s+\S+\s+strings\s*:\s*(?:#.*)?$', re.IGNORECASE)
    old_new_re = re.compile(r'^\s*(old|new)\s+')

    modified_count = 0
    for rpy_path in glob.glob(os.path.join(tl_dir, '**', '*.rpy'), recursive=True):
        try:
            with open(rpy_path, encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue

        remove = set()
        i = 0
        while i < len(lines):
            if header_re.match(lines[i].strip()):
                block_start = i
                j = i + 1
                has_content = False
                while j < len(lines):
                    if lines[j].strip() == '':
                        j += 1
                        continue
                    if not lines[j][0].isspace():
                        break
                    if old_new_re.match(lines[j]):
                        has_content = True
                    j += 1
                if not has_content:
                    end = j - 1
                    while end > block_start and lines[end].strip() == '':
                        end -= 1
                    for idx in range(block_start, end + 1):
                        remove.add(idx)
                i = j
            else:
                i += 1

        if not remove:
            continue

        new_lines = [l for idx, l in enumerate(lines) if idx not in remove]
        cleaned = []
        blank_run = 0
        for line in new_lines:
            if line.strip() == '':
                blank_run += 1
                if blank_run <= 2:
                    cleaned.append(line)
            else:
                blank_run = 0
                cleaned.append(line)

        backup_path = rpy_path + '.bak'
        if not os.path.exists(backup_path):
            shutil.copyfile(rpy_path, backup_path)
        with open(rpy_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned)
        print(f"Removed empty translate strings block(s) from: {rpy_path}")
        modified_count += 1

    return modified_count


def deduplicate_strings_blocks(tl_dir: str) -> int:
    """Remove earlier duplicate old/new pairs within translate X strings: blocks.

    When the same old string appears more than once for the same language key,
    keeps the last occurrence (newest block wins) and removes earlier ones.
    Ren'Py errors on startup when it encounters two old "X" entries for the
    same language, even across different translate strings: blocks in the same file.
    Returns the number of files modified.
    """
    header_re = re.compile(r'^translate\s+(\S+)\s+strings\s*:\s*(?:#.*)?$', re.IGNORECASE)
    old_re = re.compile(r'^\s*old\s+((\"([^\"\\]|\\.)*\")|\'([^\'\\]|\\.)*\')\s*(?:#.*)?$')

    modified_count = 0

    for rpy_path in glob.glob(os.path.join(tl_dir, '**', '*.rpy'), recursive=True):
        try:
            with open(rpy_path, encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue

        # Parse all old/new entries with their line ranges and language key.
        # Each entry = (lang_key_lower, old_text, entry_start_idx, entry_end_idx)
        # entry_start = first comment line before old (or old line itself if no comment)
        # entry_end   = new line (or old line if no new line follows)
        entries = []
        current_lang = None
        in_strings_block = False
        pending_comment_start = None

        i = 0
        while i < len(lines):
            line = lines[i]
            first_char = line[0:1]

            if first_char and not first_char.isspace() and line.strip():
                m = header_re.match(line.strip())
                if m:
                    current_lang = m.group(1)
                    in_strings_block = True
                    pending_comment_start = None
                    i += 1
                    continue
                elif not line.strip().startswith('#'):
                    in_strings_block = False
                    current_lang = None
                    pending_comment_start = None

            if not in_strings_block:
                i += 1
                continue

            stripped = line.strip()
            if stripped.startswith('#') and first_char.isspace():
                if pending_comment_start is None:
                    pending_comment_start = i
            elif stripped == '':
                pending_comment_start = None
            else:
                om = old_re.match(line)
                if om:
                    entry_start = pending_comment_start if pending_comment_start is not None else i
                    try:
                        old_text = ast.literal_eval(om.group(1))
                    except Exception:
                        old_text = om.group(1).strip("\"'")

                    # Find the following new line (skip blanks)
                    entry_end = i
                    k = i + 1
                    while k < len(lines):
                        if lines[k].strip() == '':
                            k += 1
                            continue
                        if re.match(r'^\s*new\s+', lines[k]):
                            entry_end = k
                        break

                    entries.append((current_lang, old_text, entry_start, entry_end))
                    pending_comment_start = None

            i += 1

        # Group by (lang_key, old_text); mark all but the last occurrence for removal.
        by_key = {}
        for entry in entries:
            lang, old_text, start, end = entry
            key = (lang, old_text)
            by_key.setdefault(key, []).append(entry)

        remove_indices = set()
        for key, group in by_key.items():
            if len(group) <= 1:
                continue
            for lang, old_text, start, end in group[:-1]:
                for idx in range(start, end + 1):
                    remove_indices.add(idx)

        if not remove_indices:
            continue

        new_lines = [l for idx, l in enumerate(lines) if idx not in remove_indices]

        # Collapse runs of 3+ blank lines to 2.
        cleaned = []
        blank_run = 0
        for line in new_lines:
            if line.strip() == '':
                blank_run += 1
                if blank_run <= 2:
                    cleaned.append(line)
            else:
                blank_run = 0
                cleaned.append(line)

        backup_path = rpy_path + '.bak'
        if not os.path.exists(backup_path):
            shutil.copyfile(rpy_path, backup_path)
        with open(rpy_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned)
        print(f"Removed duplicate string entries from: {rpy_path}")
        modified_count += 1

    return modified_count


def translate_strings_in_dir(tl_dir: str):
    if not os.path.isdir(tl_dir):
        print(f"Strings directory not found, skipping: {tl_dir}")
        return

    stripped = strip_empty_strings_blocks(tl_dir)
    if stripped:
        print(f"Cleaned up empty translate strings block(s) in {stripped} file(s).")

    deduped = deduplicate_strings_blocks(tl_dir)
    if deduped:
        print(f"Removed duplicate string entries in {deduped} file(s).")

    globally_translated = collect_translated_strings(tl_dir)
    print(f"Found {len(globally_translated)} globally translated strings (cross-file duplicate guard).")

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
            translate_strings_file(path, globally_translated)

    if not found_any:
        print(f"No .rpy translation files found in: {tl_dir}")


def load_original_texts(tl_dir: str) -> tuple:
    """Scan tl .rpy files; return (originals, auto_translated).
    originals: {identifier: original_english} from Ren'Py-generated blocks with comments.
    auto_translated: set of identifiers from AUTO TRANSLATION blocks (no comment = already done).
    """
    originals = {}
    auto_translated = set()
    translate_re = re.compile(r'^\s*translate\s+\S+\s+(\S+)\s*:')
    comment_re = re.compile(r'^\s*#\s*(?:\w+\s+)*"((?:[^"\\]|\\.)*)"')
    for rpy_path in glob.glob(os.path.join(tl_dir, '**', '*.rpy'), recursive=True):
        try:
            with open(rpy_path, encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue
        current_id = None
        for line in lines:
            m = translate_re.match(line)
            if m:
                current_id = m.group(1)
                continue
            if current_id is None:
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                cm = comment_re.match(line)
                if cm and current_id not in originals:
                    raw = cm.group(1)
                    originals[current_id] = raw.replace('\\"', '"').replace('\\\\', '\\')
                    current_id = None
            else:
                # Content line without preceding comment: AUTO TRANSLATION block
                if current_id not in originals:
                    auto_translated.add(current_id)
                current_id = None
    return originals, auto_translated


def migrate_auto_translations(tl_dir: str) -> int:
    """One-time migration: move AUTO TRANSLATION block content into original blocks, then remove the sections.
    Returns the number of files modified."""
    block_re = re.compile(r'^\s*translate\s+\S+\s+(\S+)\s*:')
    modified_count = 0

    for rpy_path in glob.glob(os.path.join(tl_dir, '**', '*.rpy'), recursive=True):
        try:
            with open(rpy_path, encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue

        if not any('# AUTO TRANSLATION BEGIN' in line for line in lines):
            continue

        # Phase 1: collect translations from AUTO TRANSLATION blocks
        auto_tr = {}
        in_auto = False
        cur_id = None
        for line in lines:
            if '# AUTO TRANSLATION BEGIN' in line:
                in_auto = True
                cur_id = None
                continue
            if '# AUTO TRANSLATION END' in line:
                in_auto = False
                cur_id = None
                continue
            if not in_auto:
                continue
            m = block_re.match(line)
            if m:
                cur_id = m.group(1)
                continue
            if cur_id:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    auto_tr[cur_id] = stripped
                    cur_id = None

        if not auto_tr:
            continue

        # Phase 2: apply translations to original blocks + strip AUTO TRANSLATION sections
        new_lines = []
        in_auto_section = False
        cur_id = None
        i = 0
        while i < len(lines):
            line = lines[i]

            if '# AUTO TRANSLATION BEGIN' in line:
                in_auto_section = True
                # Remove trailing blank + preceding ##### line already appended
                while new_lines and new_lines[-1].strip() == '':
                    new_lines.pop()
                if new_lines and set(new_lines[-1].strip()) == {'#'}:
                    new_lines.pop()
                while new_lines and new_lines[-1].strip() == '':
                    new_lines.pop()
                i += 1
                continue

            if in_auto_section:
                if '# AUTO TRANSLATION END' in line:
                    in_auto_section = False
                    i += 1
                    if i < len(lines) and set(lines[i].strip()) == {'#'}:
                        i += 1
                else:
                    i += 1
                continue

            m = block_re.match(line)
            if m:
                cur_id = m.group(1)
                new_lines.append(line)
                i += 1
                continue

            if cur_id and cur_id in auto_tr:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    indent = re.match(r'^\s*', line).group(0)
                    new_lines.append(indent + auto_tr[cur_id] + '\n')
                    cur_id = None
                    i += 1
                    continue
                elif stripped and stripped.startswith('#'):
                    new_lines.append(line)
                    i += 1
                    continue
            elif cur_id:
                if line.strip() and not line.strip().startswith('#'):
                    cur_id = None

            new_lines.append(line)
            i += 1

        backup_path = rpy_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copyfile(rpy_path, backup_path)
        with open(rpy_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Migrated: {rpy_path}")
        modified_count += 1

    return modified_count


def apply_translations_in_place(tl_path: str, translations: list) -> None:
    """Update translate blocks in tl_path with new translations.
    translations: [(identifier, renpy_script, original_dialogue, translated_text), ...]
    """
    if not translations:
        return

    trans_dict = {}
    for identifier, renpy_script, _orig, text in translations:
        text_for_rpy = text.replace('"', '\\"')
        script = renpy_script
        if script == "[what]":
            script = '"[what]"'
        trans_dict[identifier] = script.replace("[what]", text_for_rpy)

    try:
        with open(tl_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (IOError, UnicodeDecodeError) as e:
        print(f"Could not read {tl_path}: {e}")
        return

    block_re = re.compile(r'^\s*translate\s+\S+\s+(\S+)\s*:')
    cur_id = None
    modified = False

    for idx, line in enumerate(lines):
        m = block_re.match(line)
        if m:
            cur_id = m.group(1)
            continue
        if cur_id:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                if cur_id in trans_dict:
                    indent = re.match(r'^\s*', line).group(0)
                    lines[idx] = indent + trans_dict[cur_id] + '\n'
                    modified = True
                cur_id = None

    if modified:
        backup_path = tl_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copyfile(tl_path, backup_path)
        with open(tl_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"Updated {len(trans_dict)} translation(s) in: {tl_path}")


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
    tl_scan_dir = os.path.join(gamepath, "game", "tl", lang_dir)
    original_texts = {}
    auto_translated_ids = set()
    if os.path.isdir(tl_scan_dir):
        print(f"Migrating any existing AUTO TRANSLATION blocks to in-place format...")
        migrated = migrate_auto_translations(tl_scan_dir)
        if migrated:
            print(f"Migrated {migrated} file(s). Re-scanning...")
        print(f"Scanning tl files for already-translated identifiers...")
        original_texts, auto_translated_ids = load_original_texts(tl_scan_dir)
        print(f"Found {len(original_texts)} source-text entries, {len(auto_translated_ids)} auto-translated.")

if not skip_dialogue:
    file = open(dialogue_file, encoding='utf-8')
    sample = file.read(4096)
    file.seek(0)
    try:
        detected_delimiter = csv.Sniffer().sniff(sample, delimiters=",\t").delimiter
    except csv.Error:
        detected_delimiter = delimiter
    reader = csv.DictReader(file, delimiter=detected_delimiter, quotechar="'")
    # Normalize fieldnames: strip surrounding single quotes and unescape '' → '
    # (Ren'Py exports "Ren'Py Script" as "'Ren''Py Script'" in some formats)
    if reader.fieldnames:
        reader.fieldnames = [f.strip("'").replace("''", "'") for f in reader.fieldnames]

    tl_filename = ""
    current_tl_path = None
    pending_translations = []
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

        # Skip rows already translated (in-place or via prior auto-translation)
        if row["Identifier"] in auto_translated_ids:
            skipped_count += 1
            continue
        # Skip rows where tl file comment differs from current dialogue (already translated)
        original_en = original_texts.get(row["Identifier"])
        if original_en is not None and row["Dialogue"] != original_en:
            skipped_count += 1
            continue

        if not row.get("Filename", "").strip():
            print(f"Warning: skipping row {row_count} (malformed CSV — empty Filename): {repr(row.get('Dialogue',''))[:60]}")
            skipped_count += 1
            continue

        if tl_filename != row["Filename"]:
            # Flush buffered translations for the previous file
            if current_tl_path and pending_translations:
                apply_translations_in_place(current_tl_path, pending_translations)
                pending_translations = []

            tl_filename = row["Filename"]
            norm_tl_filename = tl_filename.replace("\\", "/")
            norm_tl_filename = re.sub(r"^game/", "", norm_tl_filename)
            norm_tl_filename = re.sub(r"^tl/[^/]+/", "", norm_tl_filename)
            current_tl_path = os.path.normpath(os.path.join(gamepath, "game", "tl", lang_dir, norm_tl_filename))
            print("Processing: " + current_tl_path)

        text = translate_text_safe(row["Dialogue"])
        translated_count += 1

        pending_translations.append((row["Identifier"], row["Ren'Py Script"], row["Dialogue"], text))

        print(tl_filename + ", " + row["Dialogue"][:60] + " -> " + text[:60])

        if row_count % 100 == 0:
            print(f"Processed {row_count} rows... (translated {translated_count}, skipped {skipped_count})")

    # Flush the last file
    if current_tl_path and pending_translations:
        apply_translations_in_place(current_tl_path, pending_translations)

    print(f"Done. Processed {row_count} rows (translated {translated_count}, skipped {skipped_count}).")
    if row_count == 0:
        print("No data rows found. Check that the delimiter matches the file and that the file contains data.")
else:
    print("Skipping dialogue rows.")

if translate_strings:
    tl_dir = os.path.join(gamepath, "game", "tl", lang_dir)
    translate_strings_in_dir(tl_dir)
