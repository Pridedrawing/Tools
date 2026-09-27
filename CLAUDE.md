# Pridedrawing Tools — Claude Code Context

Translation and voiceover pipeline for B_Engel, BoundToCollege, Gay-Office-Sim, Heritage.

## Full Workflow (per language)

```
1. Ren'Py Launcher → Generate Translations
   → Creates .rpy files in game/tl/<language>/

2. Ren'Py Launcher → Extract Dialogue (select correct language!)
   → Exports dialogue.tab to repo root (e.g. B_Engel/dialogue.tab)

3. translate/translate.py
   → Reads dialogue.tab → DeepL → writes translated blocks into game/tl/<lang>/*.rpy
   → Requires: DEEPL_API_KEY in environment

4. Missing Files/missing_files.py
   → Compares dialogue.tab against game/audio/voice/
   → Output: dialogue_missing.tab + extra_files.csv

5. voiceover/gen.py
   → Reads dialogue_missing.tab → TTS provider → saves .mp3 files
   → Requires: ELEVENLABS_API_KEY (ElevenLabs) or local Qwen model

6. Repeat from step 2 for next language
```

## Key Rules

- Never commit `tl/` changes from game repos — managed by these scripts
- Never commit `set_env.ps1` — contains live API keys (gitignored)
- `dialogue.tab` must be extracted in the **correct target language** before use
- Scripts are Windows-native; Mac paths: `~/Projects/` instead of `C:\Users\olli_\Documents\GitHub\`

## Scripts

### translate/translate.py
- Translates dialogue via DeepL, writes `translate <lang> <id>:` blocks into .rpy files
- Config: `translate/config.py` — saves game/language selections between runs
- Supports glossaries (`glossaries.json`) for consistent character names
- Masks Ren'Py placeholders `[var]` and `{tag}` before translation
- Replaces the line inside existing blocks; appends a block (with warning) when the id has none
- Migrates old `# AUTO TRANSLATION` sections into regular blocks; entries without a regular block are kept as their own block (before 2026-09-27 they were deleted — lost 340 pt / 166 es / 182 en lines in BEngel)
- Empty `""` dialogue (Ren'Py `--empty`) is translated from the block comment
- The dialogue export strips text tags, the block comment keeps them: rows are compared without tags, and a tagged untranslated line is translated from the comment so `{cps}`/`{size}` survive (before 2026-09-27 such lines were skipped forever — BEngel credits). `[..]`, `{..}` and literal `\n` are masked from DeepL
- dialogue.tab is read with `csv.QUOTE_NONE` (a line starting with `'` used to swallow the rest of the file)
- Calls `check_tl.report()` at the end

### translate/check_tl.py
- Args: `[lang_dir] [--all]`; game and default language from `translate/config.py`
- Reads tl files directly; `dialogue.tab` only supplies the current ids (warns if older than the newest source `.rpy`)
- Reports: ids without a block, empty blocks, blocks identical to the source, strings with empty/unchanged `new`; info only: short identical lines (names, interjections), orphans, blocks under another language key
- Ren'Py language keys are case-sensitive: only `translate <lang_dir>` blocks count
- Exit code 1 when problems are found

### Missing Files/missing_files.py
- Args: `[base_dir] [--dialogue path] [--lang English] [--ext .mp3]`
- `base_dir`: repo root (e.g. `~/Projects/B_Engel`) or `game/` subfolder
- Output: `dialogue_missing.tab` (feed into gen.py) + `extra_files.csv`
- Auto-detects language from dialogue.tab if `--lang` omitted

### voiceover/gen.py
- Interactive: select game, provider (elevenlabs/qwen), language, mode
- **Mode 1 (batch):** processes `dialogue_missing.tab`
- **Mode 2 (manual):** enter IDs one by one, plays back result, keep/regenerate/skip
- On skip: restores original file from `.bak` backup
- `dialogue.tab` is loaded from repo root (parent of `game/`)
- Duplicate IDs (multi-line translate blocks): uses first occurrence only
- Config: `voiceover/config.py` or `voiceover/config_11L.py`
- `_speakable()` cleans the export text before TTS: `[..]` and `{..}` removed, `\n` / `\\n` (doubled in dialogue_missing.tab) become a pause, `\"` unescaped
- Skips lines whose tl block is still the source text (`_load_untranslated_ids`: every block for the id equals the source comment, >1 word, common words of `main_lang`); otherwise the target voice records the source language and the file then counts as done. Summary shows the count; manual mode warns and asks. Only ids in the input file are counted (orphan blocks look untranslated too)
- Asks *Delete outdated voicelines of '<game>' after the run?* (default no); if yes, calls `clean_unused.run_clean(game, delete=True, list_limit=10)` after generation, in both modes

### voiceover/clean_unused.py
- Deletes voice files no current line uses; dry run unless `--delete`, confirmation unless `--yes`; `run_clean()` is the callable entry point
- Scope: only `<game>/audio/voice/` and `<game>/tl/<lang>/audio/voice/`, non-recursive, only `.mp3/.ogg/.wav` + `*.<ext>.bak`
- Used = stem in a fresh SDK extract (`renpy.exe <project> dialogue None`) or in an active `voice`/`audio/voice/...` reference in any `.rpy` (comments ignored)
- The extract overwrites `<repo>/dialogue.tab`; an existing one is saved and restored (before 2026-09-27 it was deleted)
- Safety: no evidence → nothing deleted; a folder with zero matches is refused unless `--force`; deletions logged to `log.txt`

### voiceover/providers/
- `elevenlabs_provider.py` — cloud TTS, MP3, voice name: `"GameName: Character"`
- `qwen_provider.py` — local voice cloning, WAV/MP3, voice name: `"GamePrefix_Character"`
  - Needs `ref.wav` + `ref.txt` per character in `qwen_voices_dir`
  - Does NOT support emotion tags — neutral output regardless of Ren'Py emotion

### Language Detection/language.py
- Detects language of each dialogue line via DeepL
- Requires: DEEPL_API_KEY

### Import_Transl/import_tansl.py
- Imports pre-translated CSV back into `tl/portuguese/*.rpy`
- Currently hardcoded to Portuguese — parameterize `tl_folder` for other languages

### VNavigator.py
- Parses .rpy for label/jump → generates .graphml story flowchart (yEd)

## API Keys

| Script | Key | File |
|--------|-----|------|
| translate.py | `DEEPL_API_KEY` | `Language Detection/set_env.ps1` |
| language.py | `DEEPL_API_KEY` | same |
| gen.py (ElevenLabs) | `ELEVENLABS_API_KEY` | `voiceover/set_env.ps1` |

Quick setup: `setup_keys.bat`

## Known Limitations

- Qwen TTS ignores Ren'Py emotion tags (surprised, lust, etc.) — always generates neutral tone
- Multi-line translate blocks share one ID — only the first line gets voiceover
- `dialogue.tab` must match the language being processed; wrong language = wrong audio
