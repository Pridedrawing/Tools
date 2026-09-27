#!/usr/bin/env python
"""Report untranslated lines in a Ren'Py tl folder.

Reads the tl files directly instead of trusting dialogue.tab's Dialogue column.
dialogue.tab only supplies the list of identifiers that exist in the current
source, so it must be exported after the last source change.

Usage:
    python check_tl.py                 # game and language from config.py
    python check_tl.py portuguese      # another language folder
    python check_tl.py portuguese --all  # list every finding, not just a sample

Exit code 1 if lines are missing, empty or still in the source language.
"""

import collections
import glob
import os
import re
import sys

_BLOCK_RE = re.compile(r'^\s*translate\s+(\S+)\s+(\S+)\s*:')
_COMMENT_RE = re.compile(r'^\s*#\s*(?:[\w.]+\s+)*"((?:[^"\\]|\\.)*)"')
_SAY_RE = re.compile(r'^\s*(?:[\w.]+\s+)*"((?:[^"\\]|\\.)*)"')
_OLD_RE = re.compile(r'^\s*old\s+"((?:[^"\\]|\\.)*)"')
_NEW_RE = re.compile(r'^\s*new\s+"((?:[^"\\]|\\.)*)"')
_AUDIO_RE = re.compile(r'\.(mp3|ogg|opus|wav)$', re.IGNORECASE)
_LETTERS_RE = re.compile(r'[^\W\d_]{2,}')

SAMPLE = 5


_TAG_RE = re.compile(r'\{[^}]*\}|\[[^\]]*\]|%\w')


def _is_short(text):
    """Names and interjections ("Marvin!", "Uhh.") are often identical in both languages.
    Text tags, interpolations and format codes don't count as words."""
    return len(re.findall(r'[^\W\d_]+', _TAG_RE.sub(" ", text))) <= 2


def load_live_ids(dialogue_file):
    live = {}
    with open(dialogue_file, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5 or parts[0] == "Identifier":
                continue
            live[parts[0]] = (parts[3], parts[4], parts[2])
    return live


def newest_source_mtime(gamepath):
    game_dir = os.path.join(gamepath, "game")
    tl_dir = os.path.join(game_dir, "tl")
    newest = 0.0
    for path in glob.glob(os.path.join(game_dir, "**", "*.rpy"), recursive=True):
        if os.path.abspath(path).startswith(os.path.abspath(tl_dir)):
            continue
        newest = max(newest, os.path.getmtime(path))
    return newest


def scan(tl_dir, lang):
    """Return blocks {id: (file, line_no, source, text)}, string entries and the
    number of blocks under another language key.

    Ren'Py language keys are case-sensitive: `translate english` blocks in the
    English folder belong to a language the game never selects, so they are skipped.
    """
    blocks = {}
    strings = []
    foreign = 0
    for path in glob.glob(os.path.join(tl_dir, "**", "*.rpy"), recursive=True):
        rel = os.path.relpath(path, tl_dir)
        with open(path, encoding="utf-8-sig") as f:
            lines = f.readlines()
        cur = None
        source = None
        in_strings = False
        pending_old = None
        for no, line in enumerate(lines, 1):
            m = _BLOCK_RE.match(line)
            if m:
                own = m.group(1) == lang
                if not own:
                    foreign += 1
                in_strings = own and m.group(2) == "strings"
                cur = m.group(2) if own and not in_strings else None
                source = None
                pending_old = None
                continue
            if in_strings:
                o = _OLD_RE.match(line)
                if o:
                    pending_old = o.group(1)
                    continue
                n = _NEW_RE.match(line)
                if n and pending_old is not None:
                    strings.append((rel, no, pending_old, n.group(1)))
                    pending_old = None
                continue
            if not cur:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                c = _COMMENT_RE.match(line)
                if c:
                    source = c.group(1)
                continue
            s = _SAY_RE.match(line)
            blocks[cur] = (rel, no, source, s.group(1) if s else None)
            cur = None
    return blocks, strings, foreign


def report(gamepath, lang_dir, dialogue_file, show_all=False):
    tl_dir = os.path.join(gamepath, "game", "tl", lang_dir)
    print()
    print(f"=== Translation check: {lang_dir} ===")
    if not os.path.isdir(tl_dir):
        print(f"tl folder not found: {tl_dir}")
        return 1
    if not os.path.exists(dialogue_file):
        print(f"Dialogue file not found: {dialogue_file}")
        return 1
    if os.path.getmtime(dialogue_file) < newest_source_mtime(gamepath):
        print("Warning: dialogue file is older than the newest source .rpy. "
              "Re-export it (Extract Dialogue) or the missing/orphan counts may be wrong.")

    live = load_live_ids(dialogue_file)
    blocks, strings, foreign = scan(tl_dir, lang_dir)

    missing = sorted(i for i in live if i not in blocks)
    empty, same_long, same_short = [], [], []
    for tid, (rel, no, source, text) in blocks.items():
        if tid not in live or text is None:
            continue
        if text == "" and source:
            empty.append((rel, no, tid, source))
        elif source is not None and text == source and _LETTERS_RE.search(source) and not _AUDIO_RE.search(source):
            (same_short if _is_short(source) else same_long).append((rel, no, tid, source))
    orphans = [i for i in blocks if i not in live]

    str_empty = [(rel, no, old) for rel, no, old, new in strings if new == "" and old]
    # Ren'Py's own interface strings (common.rpy) are English, so for an English
    # target they are correct as they are.
    english = lang_dir.lower().startswith("en")
    str_same = [(rel, no, old) for rel, no, old, new in strings
                if new == old and _LETTERS_RE.search(old) and not _is_short(old)
                and not (english and os.path.basename(rel) == "common.rpy")]

    def section(title, rows, fmt):
        print(f"\n{title}: {len(rows)}")
        if not rows:
            return
        by_file = collections.defaultdict(list)
        for r in rows:
            by_file[r[0]].append(r)
        for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
            items = sorted(by_file[rel], key=lambda r: int(r[1]))
            print(f"  {len(items):4}  {rel}")
            for r in (items if show_all else items[:SAMPLE]):
                print("          " + fmt(r))
            if not show_all and len(items) > SAMPLE:
                print(f"          ... {len(items) - SAMPLE} more (--all)")

    missing_rows = [(live[i][0], live[i][1], i, live[i][2]) for i in missing]
    section("Lines without a translate block (source language shows in game)", missing_rows,
            lambda r: f"line {r[1]}  {r[2]}  {r[3][:70]}")
    section("Blocks left empty (blank in game)", empty,
            lambda r: f"line {r[1]}  {r[2]}  {r[3][:70]}")
    section("Blocks identical to the source", same_long,
            lambda r: f"line {r[1]}  {r[2]}  {r[3][:70]}")
    section("Strings with empty 'new'", str_empty,
            lambda r: f"line {r[1]}  {r[2][:70]}")
    section("Strings identical to 'old'", str_same,
            lambda r: f"line {r[1]}  {r[2][:70]}")
    print(f"\nShort lines identical to the source (names, interjections; usually fine): {len(same_short)}")
    print(f"Orphan blocks (source line no longer exists; harmless): {len(orphans)}")
    if foreign:
        print(f"Blocks under another language key than '{lang_dir}' (never loaded for this language): {foreign}")

    problems = len(missing) + len(empty) + len(same_long) + len(str_empty) + len(str_same)
    print(f"\n{'OK' if not problems else str(problems) + ' problem(s) found'}.")
    return 1 if problems else 0


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)  # config.py opens glossaries.json relative to the cwd
    import config

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lang = args[0] if args else config.lang_dir
    game = config.game_dict[config.game_name]
    gamepath = os.path.normpath(game["path"])
    dfile = config.dialogue_path or os.path.join(gamepath, config.filename)
    sys.exit(report(gamepath, lang, os.path.abspath(dfile), show_all="--all" in sys.argv))
