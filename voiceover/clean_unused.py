#!/usr/bin/env python
"""Delete unused / outdated generated voicelines from a project's voice folders.

A voiceline file is considered USED when its stem (the Ren'Py auto-voice
identifier, e.g. `bedr_bell_0d700162`) appears in a fresh Ren'Py dialogue
export (`dialogue.tab`, Identifier column), or when an active .rpy reference
points at it (a `voice "..."` / `play voice` / `queue voice` statement, or any
string literal naming `audio/voice/<stem>.<ext>` -- e.g. config.sample_voice).

Scope is deliberately narrow: only `<game>/audio/voice/` and
`<game>/tl/<lang>/audio/voice/` are ever walked, and inside those folders only
the extensions the TTS providers emit (.mp3/.ogg/.wav) plus leftover `.bak`
copies are candidates. Sound effects, music and every other audio file live
outside those folders and are never touched; foreign extensions inside a voice
folder are reported but never deleted.

Evidence is a fresh SDK dialogue extract by default (language "None" -- the
identifiers are language-independent, tl folders carry same-named files). If
the extract fails, nothing is deleted. A stale export can be passed with
--dialogue instead.

Dry run by default: pass --delete to actually remove files (interactive
confirmation unless --yes). Deletions are logged to log.txt.
"""

import argparse
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

_CONFIG_MODULE_NAME = (os.environ.get("VOICEOVER_CONFIG") or "config").strip() or "config"
config = importlib.import_module(_CONFIG_MODULE_NAME)

# Extensions the TTS providers write (elevenlabs: mp3; qwen: mp3/ogg/wav via
# config.qwen_output_format). Anything else inside a voice folder is foreign.
VOICE_EXTS = {".mp3", ".ogg", ".wav"}

_DEFAULT_RENPY_EXE = r"C:\Program Files\renpy-8.4.1-sdk\renpy.exe"

# Active say-channel references. Anchored so commented-out legacy lines
# (`#voice "audio/voice/..."`) do not protect stale files.
_VOICE_STMT_RE = re.compile(r'^\s*(?:play\s+|queue\s+)?voice\s+["\']([^"\']+)["\']', flags=re.IGNORECASE)
# Any string literal naming a file under audio/voice/ (config.sample_voice,
# screen code, python blocks ...). Only applied to non-comment lines.
_AUDIO_VOICE_STR_RE = re.compile(r'["\'][^"\']*?audio/voice/([^"\'/]+)["\']', flags=re.IGNORECASE)


def _log_factory(log_path: str):
    def _log(event: str, identifier: str = "", detail: str = "") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="") as f:
            f.write(f"{timestamp}\t{event}\t{identifier}\t{detail}\n")

    return _log


def _norm(name: str) -> str:
    return name.strip().lower()


def _stem_of(value: str) -> str:
    value = value.strip().strip('"').strip("'").replace("\\", "/")
    base = value.split("/")[-1]
    if not base:
        return ""
    if "." in base:
        return os.path.splitext(base)[0]
    return base


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


def _voice_dirs(game_dir: Path) -> list[Path]:
    dirs = []
    main_voice = game_dir / "audio" / "voice"
    if main_voice.is_dir():
        dirs.append(main_voice)
    tl_root = game_dir / "tl"
    if tl_root.is_dir():
        for lang_dir in sorted(p for p in tl_root.iterdir() if p.is_dir()):
            lang_voice = lang_dir / "audio" / "voice"
            if lang_voice.is_dir():
                dirs.append(lang_voice)
    return dirs


def _run_dialogue_extract(renpy_exe: Path, project_root: Path, log) -> Path | None:
    """Run the SDK dialogue extract and return a private copy of dialogue.tab.

    The SDK writes <project_root>/dialogue.tab. That artefact is copied into a
    temp file; a dialogue.tab that existed before is put back afterwards, and
    one that did not is removed again, so the repo is left as it was.
    Returns None when the extract produced no usable file.
    """
    artifact = project_root / "dialogue.tab"
    pre_mtime = artifact.stat().st_mtime if artifact.exists() else 0.0
    started = time.time()

    # The extract overwrites <project_root>/dialogue.tab. An existing one is the
    # user's export (e.g. the target language for translate.py), so keep a copy
    # and put it back afterwards instead of leaving the repo without it.
    saved = None
    if artifact.exists():
        saved = Path(tempfile.mkdtemp(prefix="voiceover_keep_")) / "dialogue.tab"
        shutil.copy2(artifact, saved)

    def _restore() -> None:
        try:
            if saved is not None:
                shutil.copy2(saved, artifact)
            elif artifact.exists():
                artifact.unlink()
        except Exception as ex:
            print(f"Warning: could not restore {artifact}: {ex}")
            if saved is not None:
                print(f"  Your previous dialogue.tab is kept at {saved}")

    cmd = [str(renpy_exe), str(project_root), "dialogue", "None"]
    print("Running Ren'Py dialogue extract (this compiles the scripts)...")
    print("  " + " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(renpy_exe.parent),
            capture_output=True,
            text=True,
            timeout=900,
        )
    except Exception as ex:
        log("clean_extract_failed", detail=f"{ex}")
        print(f"Dialogue extract failed to run: {ex}")
        _restore()
        return None

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        log("clean_extract_failed", detail=f"exit={proc.returncode}")
        print(f"Dialogue extract exited with code {proc.returncode}:")
        for line in tail:
            print("  " + line)
        _restore()
        return None

    if not artifact.exists() or artifact.stat().st_mtime <= pre_mtime or artifact.stat().st_mtime < started - 5:
        log("clean_extract_failed", detail="dialogue.tab not refreshed")
        print("Dialogue extract ran but dialogue.tab was not (re)written.")
        _restore()
        return None

    tmp = Path(tempfile.mkdtemp(prefix="voiceover_clean_")) / "dialogue.tab"
    try:
        shutil.copy2(artifact, tmp)
    finally:
        _restore()
    return tmp


def _parse_identifiers(tab_path: Path) -> set[str]:
    ids: set[str] = set()
    with open(tab_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        header = f.readline()
        if not header or not header.startswith("Identifier"):
            return ids
        for line in f:
            line = line.rstrip("\n\r")
            if not line:
                continue
            identifier = line.split("\t", 1)[0].strip()
            if identifier:
                ids.add(_norm(identifier))
    return ids


def _scan_active_references(game_dir: Path) -> set[str]:
    stems: set[str] = set()
    for rpy in game_dir.rglob("*.rpy"):
        try:
            text = rpy.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            match = _VOICE_STMT_RE.match(line)
            if match:
                stem = _stem_of(match.group(1))
                if stem:
                    stems.add(_norm(stem))
                continue
            for match in _AUDIO_VOICE_STR_RE.finditer(line):
                stem = _stem_of(match.group(1))
                if stem:
                    stems.add(_norm(stem))
    return stems



def _print_names(items: list[tuple[Path, str]], limit: int | None) -> None:
    ordered = sorted(items, key=lambda item: item[1])
    shown = ordered if limit is None else ordered[:limit]
    for path, _key in shown:
        print(f"    {path.name}")
    if len(ordered) > len(shown):
        print(f"    ... and {len(ordered) - len(shown)} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report and delete unused/outdated generated voicelines (dry run by default).",
    )
    parser.add_argument("--game", dest="game_name", help="Game name (must match a key in config.game_dict)")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete the unused files (default: report only)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation (only meaningful with --delete)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the overlap guard that refuses a folder whose files share no identifier with the evidence",
    )
    parser.add_argument(
        "--dialogue",
        dest="dialogue_path",
        help="Use an existing dialogue export (.tab) as evidence instead of running a fresh SDK extract",
    )
    parser.add_argument("--renpy", dest="renpy_exe", help="Path to the Ren'Py SDK executable")
    parser.add_argument("--log", dest="log_path", help="Path to log file (default: Tools/voiceover/log.txt)")
    args = parser.parse_args()

    selected_game_name = args.game_name or config.game_name
    if not args.game_name and sys.stdin is not None and sys.stdin.isatty():
        selected_game_name = _prompt_game(selected_game_name)
    return run_clean(
        selected_game_name,
        delete=args.delete,
        assume_yes=args.yes,
        force=args.force,
        dialogue_path=args.dialogue_path,
        renpy_exe=args.renpy_exe,
        log_path=args.log_path,
    )


def run_clean(
    selected_game_name: str,
    *,
    delete: bool = False,
    assume_yes: bool = False,
    force: bool = False,
    dialogue_path: str | None = None,
    renpy_exe: str | None = None,
    log_path: str | None = None,
    list_limit: int | None = None,
) -> int:
    """Report (and with delete=True remove) unused voicelines of one game.

    Only that game's audio/voice folder and its tl/<lang>/audio/voice folders
    are touched. With delete=True the user is still asked to confirm unless
    assume_yes is set. list_limit caps the file names listed per folder
    (None = list all). Returns 0 on success, 1 if aborted, 2 on error.
    """
    script_dir = Path(__file__).resolve().parent
    log_path = log_path or str(script_dir / "log.txt")
    log = _log_factory(log_path)

    if selected_game_name not in config.game_dict:
        print(f"Unknown game '{selected_game_name}'. Known: {', '.join(config.game_dict.keys())}")
        return 2
    game = config.game_dict[selected_game_name]

    game_dir = Path(game["savepath"])
    project_root = game_dir.parent
    if not game_dir.is_dir():
        print(f"Game directory not found: {game_dir}")
        return 2

    print("Game: " + selected_game_name)
    print("Game dir: " + str(game_dir))
    print("Mode: " + ("DELETE" if delete else "dry run (report only)"))
    print("================================")

    voice_dirs = _voice_dirs(game_dir)
    if not voice_dirs:
        print(f"No audio/voice folders found under {game_dir} (or its tl languages). Nothing to do.")
        return 0

    if dialogue_path:
        evidence_path = Path(dialogue_path)
        if not evidence_path.exists():
            print(f"Dialogue export not found: {evidence_path}")
            return 2
        print("Evidence: supplied export " + str(evidence_path))
    else:
        renpy_path = Path(renpy_exe or getattr(config, "renpy_exe", "") or _DEFAULT_RENPY_EXE)
        if not renpy_path.exists():
            print(f"Ren'Py SDK executable not found: {renpy_path}")
            print("Pass --renpy <path> or set renpy_exe in config.py, or supply --dialogue <export>.")
            return 2
        evidence_path = _run_dialogue_extract(renpy_path, project_root, log)
        if evidence_path is None:
            print("No evidence available - refusing to delete anything. Supply --dialogue <export> to retry.")
            return 2
        print("Evidence: fresh extract " + str(evidence_path))

    referenced = _parse_identifiers(evidence_path)
    if not referenced:
        print(f"Evidence export {evidence_path} contains no identifiers - refusing to delete anything.")
        return 2
    referenced |= _scan_active_references(game_dir)
    print(f"Referenced identifiers (export + active .rpy references): {len(referenced)}")

    total_unused: list[tuple[Path, str]] = []
    total_baks: list[tuple[Path, str]] = []
    refused_dirs: list[str] = []

    for voice_dir in voice_dirs:
        files = [p for p in voice_dir.iterdir() if p.is_file()]
        used = 0
        unused: list[tuple[Path, str]] = []
        baks: list[tuple[Path, str]] = []
        ignored: list[str] = []
        for path in files:
            name = path.name
            if name.lower().endswith(".bak"):
                inner_suffix = os.path.splitext(os.path.splitext(name)[0])[1].lower()
                if inner_suffix in VOICE_EXTS:
                    baks.append((path, _norm(os.path.splitext(name)[0])))
                else:
                    ignored.append(name)
                continue
            if path.suffix.lower() not in VOICE_EXTS:
                ignored.append(name)
                continue
            key = _norm(path.stem)
            if key in referenced:
                used += 1
            else:
                unused.append((path, key))

        overlap = used > 0 or any(key in referenced for _path, key in baks)
        if not overlap and files and not force:
            refused_dirs.append(str(voice_dir))
            print(f"\n[{voice_dir}]")
            print(f"  REFUSED: none of its {len(files)} files matches any referenced identifier.")
            print("  The evidence and this folder likely use different identifier schemes (or the")
            print("  wrong export). Re-run with --force only if you are sure the whole folder is stale.")
            continue

        total_unused.extend(unused)
        total_baks.extend(baks)

        unused_bytes = sum(p.stat().st_size for p, _ in unused)
        bak_bytes = sum(p.stat().st_size for p, _ in baks)
        print(f"\n[{voice_dir}]")
        print(f"  files: {len(files)}  used: {used}  unused: {len(unused)}  leftover .bak: {len(baks)}")
        if ignored:
            shown = ", ".join(sorted(ignored)[:8])
            more = " ..." if len(ignored) > 8 else ""
            print(f"  ignored (foreign extension, never deleted): {len(ignored)} -> {shown}{more}")
        if unused:
            print(f"  unused voicelines ({unused_bytes / 1048576:.1f} MiB):")
            _print_names(unused, list_limit)
        if baks:
            print(f"  leftover .bak copies ({bak_bytes / 1048576:.1f} MiB):")
            _print_names(baks, list_limit)

    candidates = total_unused + total_baks
    print("\n================================")
    print(f"Total unused voicelines: {len(total_unused)}")
    print(f"Total leftover .bak copies: {len(total_baks)}")
    if refused_dirs:
        print(f"Refused folders (see above): {len(refused_dirs)}")
    if not candidates:
        print("Nothing to delete.")
        log("clean_run", detail=f"game={selected_game_name} unused=0 baks=0 mode={'delete' if delete else 'dry'}")
        return 0

    freed = sum(p.stat().st_size for p, _ in candidates)
    print(f"Would free: {freed / 1048576:.1f} MiB")

    if not delete:
        print("\nDry run - no files deleted. Re-run with --delete to remove them.")
        log("clean_run", detail=f"game={selected_game_name} unused={len(total_unused)} baks={len(total_baks)} mode=dry")
        return 0

    if not assume_yes:
        answer = input(f"\nDelete {len(candidates)} files ({freed / 1048576:.1f} MiB)? (y/N) ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted - nothing deleted.")
            return 1

    deleted = 0
    failed = 0
    for path, key in candidates:
        try:
            path.unlink()
            deleted += 1
            log("deleted_unused", key, str(path))
        except Exception as ex:
            failed += 1
            log("delete_failed", key, f"{path}: {ex}")
            print(f"  FAILED to delete {path}: {ex}")

    print(f"\nDeleted: {deleted}  Failed: {failed}")
    log("clean_run", detail=f"game={selected_game_name} deleted={deleted} failed={failed} mode=delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

